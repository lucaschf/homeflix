"""Catalog visibility is written in exactly one module.

``ViewingPolicy.permits()`` defines what a profile may see, and
``_visibility_filter.py`` projects that definition into SQL (ADR-017,
ADR-035 §7). ``test_visibility_projection.py`` holds the projection to
the definition, but only for the read paths it enumerates. What keeps a
new or rewritten read path from growing its own, subtly different copy
is this rule: in the catalog repositories, nothing but the funnel may
build a predicate over the ``library_id`` or ``minimum_age`` columns.

The rule is total, with no allowlist of files or lines. Filters over
those columns that are *not* viewing gates — the admin single-library
param, the enrichment-review worklist — have named helpers inside the
funnel, which is what lets this test stay absolute.

Why the AST and not grep:

- The columns also appear in shapes that are not predicates, such as
  ``select(MovieModel.library_id)`` and ``group_by`` in the per-library
  size totals. The detector only inspects comparison operands, the
  receiver of a column operator such as ``.in_`` or ``.is_``, and
  ``filter_by`` keywords.
- ``scan_run_repository.py`` filters ``ScanRunModel.library_id`` in the
  same directory. The owner of the attribute is resolved against the
  module's globals, so a class that is provably not a catalog model is
  exempt by type. Anything that cannot be resolved — a ``model``
  parameter, an ``aliased()`` entity, ``__table__.c`` — counts as
  catalog: the generic ``model.library_id`` shape is exactly the one a
  new shared helper would use, so the detector fails closed on it.

Raw SQL cannot be resolved to a model, so string literals (documentation
aside) are matched with a narrow pattern: a gated column name directly
followed by a comparison. The admin FTS helpers
(``_movie_fts_matching_ids``, ``_series_fts_matching_ids``) are still
written as raw SQL, which makes them the likeliest place for an inline
copy to reappear.

This is a guardrail against drift, not a sandbox: routing a column
through a local variable before comparing it escapes the scan. It also
cannot see Python-side filtering in use cases (``get_featured_media``,
``search_catalog``), which sits outside the repositories entirely.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from src.modules.media.infrastructure.persistence.models.movie import MovieModel
from src.modules.media.infrastructure.persistence.models.scan_run import ScanRunModel
from src.modules.media.infrastructure.persistence.models.series import SeriesModel

if TYPE_CHECKING:
    from collections.abc import Mapping

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORIES_DIR = _REPO_ROOT / "src/modules/media/infrastructure/persistence/repositories"
_FUNNEL = _REPOSITORIES_DIR / "_visibility_filter.py"

_GATED_COLUMNS = frozenset({"library_id", "minimum_age"})
_CATALOG_MODELS = (MovieModel, SeriesModel)

# ``ColumnOperators`` methods that turn a column into a condition.
# Ordering and labelling (``asc``, ``desc``, ``label``) are left out on
# purpose: they project a column, they do not filter on it.
_COLUMN_PREDICATE_METHODS = frozenset(
    {
        "between",
        "bool_op",
        "contains",
        "endswith",
        "icontains",
        "iendswith",
        "ilike",
        "in_",
        "is_",
        "is_distinct_from",
        "is_not",
        "is_not_distinct_from",
        "isnot",
        "isnot_distinct_from",
        "istartswith",
        "like",
        "match",
        "not_ilike",
        "not_in",
        "not_like",
        "notilike",
        "notin_",
        "notlike",
        "op",
        "regexp_match",
        "startswith",
    }
)

_RAW_SQL_PREDICATE = re.compile(
    r"\b(?:library_id|minimum_age)\b\s*"
    r"(?:[=<>!]|(?:NOT\s+)?IN\b|IS\b|BETWEEN\b|(?:NOT\s+)?LIKE\b|GLOB\b)",
    re.IGNORECASE,
)


def _owner_may_be_catalog(owner: ast.expr, namespace: Mapping[str, object]) -> bool:
    """Whether the object an attribute hangs off could be a catalog model.

    Only a module-level name bound to a class that is not a catalog
    model is ruled out; everything else fails closed.
    """
    if isinstance(owner, ast.Name):
        resolved = namespace.get(owner.id)
        if isinstance(resolved, type) and not issubclass(resolved, _CATALOG_MODELS):
            return False
    return True


def _reads_gated_column(expr: ast.expr, namespace: Mapping[str, object]) -> bool:
    """Whether evaluating ``expr`` reads a gated catalog column, or might.

    Walks the whole expression so wrappers such as
    ``func.coalesce(MovieModel.minimum_age, 0)`` are still caught, and
    treats a bare column-name literal as a read so ``column("library_id")``
    and ``getattr(MovieModel, "minimum_age")`` are too.
    """
    for node in ast.walk(expr):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in _GATED_COLUMNS
            and _owner_may_be_catalog(node.value, namespace)
        ):
            return True
        if isinstance(node, ast.Constant) and node.value in _GATED_COLUMNS:
            return True
    return False


def _is_inline_predicate(
    node: ast.AST,
    namespace: Mapping[str, object],
    documentation: set[int],
) -> bool:
    """Whether a single AST node builds a predicate over a gated column."""
    if isinstance(node, ast.Compare):
        operands = (node.left, *node.comparators)
        return any(_reads_gated_column(operand, namespace) for operand in operands)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in _COLUMN_PREDICATE_METHODS:
            return _reads_gated_column(node.func.value, namespace)
        if node.func.attr == "filter_by":
            return any(keyword.arg in _GATED_COLUMNS for keyword in node.keywords)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return id(node) not in documentation and _RAW_SQL_PREDICATE.search(node.value) is not None
    return False


def _find_inline_predicates(source: str, namespace: Mapping[str, object]) -> list[str]:
    """List every predicate over a gated column built in ``source``.

    Args:
        source: Python source of one module.
        namespace: That module's globals, used to resolve which class an
            attribute belongs to.

    Returns:
        ``line N: <code>`` entries, sorted by line; empty when clean.
    """
    tree = ast.parse(source)
    # A string that is only an expression statement (a docstring, an
    # attribute docstring) cannot reach a query.
    documentation = {
        id(statement.value)
        for statement in ast.walk(tree)
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
    }
    found = {
        (node.lineno, ast.unparse(node))
        for node in ast.walk(tree)
        if _is_inline_predicate(node, namespace, documentation)
    }
    return [f"line {line}: {code}" for line, code in sorted(found)]


def _scanned_files() -> list[Path]:
    return sorted(path for path in _REPOSITORIES_DIR.rglob("*.py") if path != _FUNNEL)


def _module_namespace(path: Path) -> Mapping[str, object]:
    parts = path.relative_to(_REPO_ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return vars(importlib.import_module(".".join(parts)))


class TestCatalogRepositoriesUseTheFunnel:
    """No catalog repository builds a visibility predicate of its own."""

    def test_scan_reaches_the_catalog_repositories(self):
        """A moved directory must fail loudly instead of passing on zero files."""
        names = {path.name for path in _scanned_files()}

        assert _FUNNEL.is_file()
        assert {"movie_repository.py", "series_repository.py", "_genre_helpers.py"} <= names

    @pytest.mark.parametrize("path", _scanned_files(), ids=lambda path: path.name)
    def test_repository_has_no_inline_visibility_predicate(self, path):
        violations = _find_inline_predicates(
            path.read_text(encoding="utf-8"), _module_namespace(path)
        )

        assert not violations, (
            f"{path.name} builds a library_id/minimum_age predicate inline. "
            "Route it through _visibility_filter.py instead:\n" + "\n".join(violations)
        )

    def test_funnel_itself_would_be_flagged(self):
        """Positive control: exempting the funnel is what keeps it green.

        The funnel writes its predicates against a ``model`` parameter,
        the generic shape a second copy would most likely take.
        """
        violations = "\n".join(
            _find_inline_predicates(_FUNNEL.read_text(encoding="utf-8"), _module_namespace(_FUNNEL))
        )

        assert "model.library_id.in_(" in violations
        assert "model.minimum_age <= limit.value" in violations
        assert "model.minimum_age.is_(None)" in violations
        assert "model.library_id == library_id" in violations


_SNIPPET_NAMESPACE: dict[str, object] = {
    "MovieModel": MovieModel,
    "SeriesModel": SeriesModel,
    "ScanRunModel": ScanRunModel,
}


class TestDetector:
    """The rule is only as strong as the shapes the detector recognizes."""

    @pytest.mark.parametrize(
        "snippet",
        [
            "stmt = select(MovieModel).where(MovieModel.library_id.in_(ids))",
            "conditions.append(SeriesModel.library_id == library_id)",
            "stmt = stmt.where(library_id == MovieModel.library_id)",
            "stmt = stmt.where(~MovieModel.library_id.in_(ids))",
            "stmt = stmt.where(SeriesModel.library_id.not_in(ids))",
            "stmt = stmt.where(MovieModel.minimum_age <= 12)",
            "stmt = stmt.where(MovieModel.minimum_age.is_(None))",
            "stmt = stmt.where(SeriesModel.minimum_age.is_not(None))",
            "stmt = stmt.where(func.coalesce(MovieModel.minimum_age, 0) <= 12)",
            "stmt = stmt.where(model.library_id.in_(ids))",
            "stmt = stmt.where(aliased(MovieModel).minimum_age < 18)",
            "stmt = stmt.where(MovieModel.__table__.c.library_id == lib)",
            "stmt = stmt.where(column('library_id') == lib)",
            "stmt = select(MovieModel).filter_by(library_id=lib)",
            'sql = "SELECT id FROM movies m WHERE m.library_id IN (:ids)"',
            'sql = f"SELECT id FROM series WHERE minimum_age <= {limit}"',
            'sql = "SELECT id FROM movies WHERE minimum_age IS NULL"',
        ],
    )
    def test_flags_inline_predicate(self, snippet):
        assert _find_inline_predicates(snippet, _SNIPPET_NAMESPACE)

    @pytest.mark.parametrize(
        "snippet",
        [
            "stmt = select(MovieModel.library_id, func.sum(size))"
            ".group_by(MovieModel.library_id)",
            "stmt = select(SeriesModel).order_by(SeriesModel.minimum_age.desc())",
            "stmt = stmt.where(ScanRunModel.library_id == library_id)",
            "stmt = stmt.where(MovieModel.id.in_(ids))",
            "stmt = insert(MovieModel).values(library_id=lib, minimum_age=age)",
            "if library_id is not None:\n    pass",
            'sql = "SELECT m.id, m.library_id, m.minimum_age FROM movies m"',
            'def f():\n    """Keep rows whose library_id IN the allowed set."""',
        ],
    )
    def test_ignores_non_predicate(self, snippet):
        assert not _find_inline_predicates(snippet, _SNIPPET_NAMESPACE)
