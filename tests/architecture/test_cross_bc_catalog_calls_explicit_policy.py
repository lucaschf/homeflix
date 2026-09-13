"""Cross-BC catalog reads name the viewing policy they apply.

The catalog repositories take ``policy: ViewingPolicy | None = None``,
and the visibility funnel renders ``None`` as no condition at all
(``_visibility_filter.py``, ADR-035 §7). Inside Media that default is
the ungated internal read the scanner and the admin paths rely on. From
another BC it is a fail-open with no symptom: a lookup that forgets the
argument answers for every title, and no test notices, because every
title the fixtures seed is visible anyway.

The rule, for every module under ``src/modules/`` outside ``media`` that
imports from ``src.modules.media``: a call whose receiver ends in
``.movies``, ``.series`` or ``.catalog_access``, to a method that
declares a ``policy`` parameter on the matching Media contract —
``MovieRepository``, ``SeriesRepository`` or ``CatalogAccessReader`` —
must pass ``policy=`` by keyword. ``policy=None`` is accepted, because
then the ungated read is a decision someone wrote down, not a default
someone forgot.

Why the receiver and the contracts, and not the method name: names such
as ``find_by_id`` and ``find_by_ids`` are shared with a dozen unrelated
repositories (``custom_lists``, ``profiles``, ``catalog_requests``), so
matching on the name alone flags legitimate calls, while a policy-taking
method with a distinctive name (``series.find_by_episode_id``) is exactly
the one a hand-kept list would miss. Which methods take ``policy`` is
read off the contracts by introspection, so a method added to a
repository later is covered without touching this file.

This is a guardrail against drift, not a sandbox: a module that reaches
a Media UoW without importing from ``src.modules.media``, or binds a
repository to a local name before calling it, escapes the scan.
"""

from __future__ import annotations

import ast
import inspect
import typing
from pathlib import Path

import pytest

from src.modules.media.application.unit_of_work import MediaUnitOfWork
from src.modules.media.domain.repositories import (
    CatalogAccessReader,
    MovieRepository,
    SeriesRepository,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULES_DIR = _REPO_ROOT / "src/modules"
_MEDIA_PACKAGE = "src.modules.media"
_POLICY_PARAMETER = "policy"

#: Media UoW attribute a call's receiver ends in → the contract it is typed as.
_CATALOG_RECEIVERS: dict[str, type] = {
    "movies": MovieRepository,
    "series": SeriesRepository,
    "catalog_access": CatalogAccessReader,
}


def _policy_methods(contract: type) -> frozenset[str]:
    """Names of the contract's methods that declare a ``policy`` parameter."""
    return frozenset(
        name
        for name, member in inspect.getmembers(contract, inspect.isfunction)
        if _POLICY_PARAMETER in inspect.signature(member).parameters
    )


_POLICY_METHODS: dict[str, frozenset[str]] = {
    receiver: _policy_methods(contract) for receiver, contract in _CATALOG_RECEIVERS.items()
}


def _imports_media(tree: ast.Module) -> bool:
    """Whether the module imports anything from the Media BC."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            continue
        if any(name == _MEDIA_PACKAGE or name.startswith(f"{_MEDIA_PACKAGE}.") for name in names):
            return True
    return False


def _catalog_calls(tree: ast.Module) -> list[ast.Call]:
    """Calls to a policy-taking method through a ``.movies``/``.series``/``.catalog_access`` receiver."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr in _POLICY_METHODS
        and node.func.attr in _POLICY_METHODS[node.func.value.attr]
    ]


def _names_policy(call: ast.Call) -> bool:
    """Whether the call passes ``policy=`` as an explicit keyword (``**kwargs`` does not count)."""
    return any(keyword.arg == _POLICY_PARAMETER for keyword in call.keywords)


def _find_calls_without_policy(source: str) -> list[str]:
    """List the catalog calls in ``source`` that leave ``policy`` to its default.

    Args:
        source: Python source of one module.

    Returns:
        ``line N: <code>`` entries, sorted by line; empty when clean.
    """
    tree = ast.parse(source)
    found = {
        (call.lineno, ast.unparse(call)) for call in _catalog_calls(tree) if not _names_policy(call)
    }
    return [f"line {line}: {code}" for line, code in sorted(found)]


def _scanned_files() -> list[Path]:
    """Modules outside Media that import from it."""
    return sorted(
        path
        for path in _MODULES_DIR.rglob("*.py")
        if path.relative_to(_MODULES_DIR).parts[0] != "media"
        and _imports_media(ast.parse(path.read_text(encoding="utf-8")))
    )


def _label(path: Path) -> str:
    return path.relative_to(_MODULES_DIR).as_posix()


class TestCrossBcCatalogCallsNamePolicy:
    """No BC outside Media leaves a catalog read's ``policy`` to its default."""

    def test_receivers_match_the_media_unit_of_work(self):
        """The receivers checked are the UoW attributes, typed as the contracts introspected."""
        hints = typing.get_type_hints(MediaUnitOfWork)

        assert {receiver: hints[receiver] for receiver in _CATALOG_RECEIVERS} == _CATALOG_RECEIVERS

    def test_introspection_finds_the_policy_taking_methods(self):
        """An empty method set would let every call through."""
        assert {"find_by_id", "find_by_ids"} <= _POLICY_METHODS["movies"]
        assert {"find_by_id", "find_by_ids", "find_by_episode_id"} <= _POLICY_METHODS["series"]
        assert {"find_movie_access", "find_series_access"} <= _POLICY_METHODS["catalog_access"]
        assert "count_under_paths" not in _POLICY_METHODS["movies"] | _POLICY_METHODS["series"]

    def test_scan_reaches_the_known_adapters(self):
        """A moved adapter or a broken detector must fail loudly instead of passing on nothing."""
        contexts_with_calls = {
            path.relative_to(_MODULES_DIR).parts[0]
            for path in _scanned_files()
            if _catalog_calls(ast.parse(path.read_text(encoding="utf-8")))
        }

        assert {"collections", "watch_progress", "streaming"} <= contexts_with_calls

    @pytest.mark.parametrize("path", _scanned_files(), ids=_label)
    def test_catalog_calls_pass_policy_by_keyword(self, path):
        violations = _find_calls_without_policy(path.read_text(encoding="utf-8"))

        assert not violations, (
            f"{_label(path)} calls a Media catalog read without policy=. The default "
            "applies no visibility filter at all; pass the caller's policy, or write "
            "policy=None where the ungated read is intended:\n" + "\n".join(violations)
        )


class TestDetector:
    """The rule is only as strong as the shapes the detector recognizes."""

    @pytest.mark.parametrize(
        "snippet",
        [
            "uow.movies.find_by_id(MovieId(movie_id))",
            "uow.series.find_by_episode_id(EpisodeId(episode_id))",
            "uow.catalog_access.find_movie_access(ids)",
            "self._uow.series.find_by_ids(ids)",
            # Positional is not a written-down decision about the gate.
            "uow.movies.find_by_ids(ids, policy)",
            # A spread may or may not carry it.
            "uow.movies.find_by_ids(ids, **kwargs)",
            "await (await factory()).movies.find_by_tmdb_ids(ids)",
        ],
    )
    def test_flags_calls_without_policy_keyword(self, snippet):
        assert _find_calls_without_policy(snippet)

    @pytest.mark.parametrize(
        "snippet",
        [
            "uow.movies.find_by_ids(ids, policy=policy)",
            "uow.movies.find_by_id(MovieId(movie_id), policy=None)",
            "uow.catalog_access.find_series_access(ids, policy=policy)",
            # Methods that take no policy on the contract.
            "uow.movies.count_under_paths(paths)",
            "uow.series.save(series)",
            # Same method names, receivers that are not the catalog.
            "uow.custom_lists.find_by_id(list_id, profile_id)",
            "uow.catalog_requests.find_by_tmdb_ids(ids, MediaType.MOVIE)",
            "movies.find_by_ids(ids)",
            # A mapping attribute that happens to be called ``movies``.
            "display.movies.get(media_id)",
        ],
    )
    def test_ignores_calls_that_name_policy_or_are_not_catalog_reads(self, snippet):
        assert not _find_calls_without_policy(snippet)

    def test_media_import_detection(self):
        assert _imports_media(ast.parse("from src.modules.media.domain import x"))
        assert _imports_media(ast.parse("import src.modules.media.application.unit_of_work"))
        assert _imports_media(
            ast.parse("if TYPE_CHECKING:\n    from src.modules.media.application import y")
        )
        assert not _imports_media(ast.parse("from src.modules.media_tools import z"))
        assert not _imports_media(ast.parse("from src.modules.collections import w"))
