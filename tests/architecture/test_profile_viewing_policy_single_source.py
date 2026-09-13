"""A profile becomes a ``ViewingPolicy`` in exactly one place.

``Profile.viewing_policy()`` is that place. Each BC that gates the
catalog by profile keeps a local ``ProfileViewingPolicyAdapter``
(ADR-009, ADR-035 §6), and every copy used to assemble the policy
field by field from ``Profile``. A new axis — the maturity limit — would
then have to be remembered in each copy, and a forgotten one would
leave its BC fail-open on that axis with no test failing, since no
production policy carries the axis yet.

The rule, for every
``src/modules/*/infrastructure/acl/profile_viewing_policy_adapter.py``:

- the only ``ViewingPolicy`` the file builds is the deny-all literal
  ``ViewingPolicy(allowed_library_ids=[])``, returned for a missing
  profile (ADR-035 §5);
- every ``return`` in ``find_for_profile`` hands back either that
  deny-all literal or ``<profile>.viewing_policy()`` itself, untouched —
  so the policy a known profile gets is exactly the one ``Profile``
  derives. Calling ``.viewing_policy()`` and then editing the result
  (``.with_updates(maturity_limit=None)``, ``.model_copy(...)``) is the
  quiet way an adapter would drop a new axis, so it is rejected too.

Why the AST and not grep: the forbidden construction has more spellings
than one pattern holds — wrapped across lines by the formatter, an
import alias, ``content_policy.ViewingPolicy``, or a classmethod such as
``ViewingPolicy.unrestricted``.

This is a guardrail against drift, not a sandbox: binding the class or
the derived policy to a local variable and returning that variable
escapes the scan.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADAPTER_GLOB = "src/modules/*/infrastructure/acl/profile_viewing_policy_adapter.py"

_POLICY_CLASS = "ViewingPolicy"
_DENY_ALL_FIELD = "allowed_library_ids"
_DERIVATION_METHOD = "viewing_policy"


def _policy_class_names(tree: ast.Module) -> frozenset[str]:
    """Names the module binds to ``ViewingPolicy``, import aliases included."""
    aliases = {
        alias.asname
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == _POLICY_CLASS and alias.asname
    }
    return frozenset({_POLICY_CLASS, *aliases})


def _refers_to_policy_class(expr: ast.expr, names: frozenset[str]) -> bool:
    """Whether ``expr`` names the class itself, bare or module-qualified."""
    if isinstance(expr, ast.Name):
        return expr.id in names
    return isinstance(expr, ast.Attribute) and expr.attr == _POLICY_CLASS


def _builds_policy(call: ast.Call, names: frozenset[str]) -> bool:
    """Whether a call constructs a ``ViewingPolicy``, in any spelling.

    Covers the constructor and any classmethod reached through the class
    (``unrestricted``, ``model_validate``, ``model_construct``).
    """
    if _refers_to_policy_class(call.func, names):
        return True
    return isinstance(call.func, ast.Attribute) and _refers_to_policy_class(call.func.value, names)


def _is_deny_all_literal(call: ast.Call, names: frozenset[str]) -> bool:
    """Whether a call is exactly ``ViewingPolicy(allowed_library_ids=[])``."""
    if not _refers_to_policy_class(call.func, names) or call.args:
        return False
    if len(call.keywords) != 1:
        return False
    keyword = call.keywords[0]
    return (
        keyword.arg == _DENY_ALL_FIELD
        and isinstance(keyword.value, ast.List)
        and not keyword.value.elts
    )


def _find_policy_constructions(source: str) -> list[str]:
    """List every ``ViewingPolicy`` built in ``source`` other than deny-all.

    Args:
        source: Python source of one module.

    Returns:
        ``line N: <code>`` entries, sorted by line; empty when clean.
    """
    tree = ast.parse(source)
    names = _policy_class_names(tree)
    found = {
        (node.lineno, ast.unparse(node))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _builds_policy(node, names)
        and not _is_deny_all_literal(node, names)
    }
    return [f"line {line}: {code}" for line, code in sorted(found)]


_ADAPTER_METHOD = "find_for_profile"


def _is_bare_derivation(expr: ast.expr) -> bool:
    """Whether ``expr`` is exactly ``<something>.viewing_policy()``, unmodified."""
    return (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr == _DERIVATION_METHOD
        and not expr.args
        and not expr.keywords
    )


def _find_non_derived_returns(source: str) -> list[str]:
    """List the returns of ``find_for_profile`` that are not derived or deny-all.

    Args:
        source: Python source of one adapter module.

    Returns:
        ``line N: <code>`` entries for every offending ``return``, plus a
        sentinel entry when the method is missing or never returns the
        derived policy; empty when clean.
    """
    tree = ast.parse(source)
    names = _policy_class_names(tree)
    methods = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == _ADAPTER_METHOD
    ]
    if not methods:
        return [f"no {_ADAPTER_METHOD} method found"]

    offending: list[str] = []
    derives = False
    for method in methods:
        for node in ast.walk(method):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            if _is_bare_derivation(node.value):
                derives = True
            elif not (isinstance(node.value, ast.Call) and _is_deny_all_literal(node.value, names)):
                offending.append(f"line {node.lineno}: {ast.unparse(node)}")

    if not derives:
        offending.append(f"{_ADAPTER_METHOD} never returns <profile>.viewing_policy()")
    return offending


def _adapter_files() -> list[Path]:
    return sorted(_REPO_ROOT.glob(_ADAPTER_GLOB))


def _bounded_context(path: Path) -> str:
    return path.relative_to(_REPO_ROOT / "src/modules").parts[0]


class TestProfileViewingPolicyAdaptersDeriveFromProfile:
    """No adapter assembles a viewing policy from ``Profile`` fields."""

    def test_scan_reaches_the_adapters(self):
        """A moved or renamed adapter must fail loudly instead of passing on zero files."""
        contexts = {_bounded_context(path) for path in _adapter_files()}

        assert {"media", "collections"} <= contexts

    @pytest.mark.parametrize("path", _adapter_files(), ids=_bounded_context)
    def test_adapter_builds_no_policy_but_deny_all(self, path):
        violations = _find_policy_constructions(path.read_text(encoding="utf-8"))

        assert not violations, (
            f"{_bounded_context(path)}'s {path.name} builds a ViewingPolicy other than "
            "the deny-all literal ViewingPolicy(allowed_library_ids=[]). Return "
            "profile.viewing_policy() instead, so a new axis is added in one place:\n"
            + "\n".join(violations)
        )

    @pytest.mark.parametrize("path", _adapter_files(), ids=_bounded_context)
    def test_adapter_returns_the_derived_policy_untouched(self, path):
        offending = _find_non_derived_returns(path.read_text(encoding="utf-8"))

        assert not offending, (
            f"{_bounded_context(path)}'s {path.name} must return either "
            "ViewingPolicy(allowed_library_ids=[]) or profile.viewing_policy() as is; "
            "editing the derived policy drops whatever axis Profile adds:\n" + "\n".join(offending)
        )


class TestDetector:
    """The rule is only as strong as the shapes the detector recognizes."""

    @pytest.mark.parametrize(
        "snippet",
        [
            # The shape every adapter had before Profile.viewing_policy().
            "return ViewingPolicy(allowed_library_ids=profile.allowed_library_ids)",
            # The copy a new axis would have to be remembered in.
            "return ViewingPolicy(\n"
            "    allowed_library_ids=profile.allowed_library_ids,\n"
            "    maturity_limit=profile.maturity_limit,\n"
            ")",
            "return ViewingPolicy(allowed_library_ids=[], maturity_limit=profile.maturity_limit)",
            "return ViewingPolicy(allowed_library_ids=[*profile.allowed_library_ids])",
            "return ViewingPolicy(allowed_library_ids=())",
            "return ViewingPolicy(**fields)",
            "return ViewingPolicy.unrestricted(profile.allowed_library_ids)",
            "return ViewingPolicy.model_validate({'allowed_library_ids': ids})",
            "return ViewingPolicy.model_construct(allowed_library_ids=[])",
            "return content_policy.ViewingPolicy(allowed_library_ids=ids)",
            "from src.shared_kernel.content_policy import ViewingPolicy as Policy\n"
            "return Policy(allowed_library_ids=ids)",
        ],
    )
    def test_flags_policy_construction(self, snippet):
        assert _find_policy_constructions(snippet)

    @pytest.mark.parametrize(
        "snippet",
        [
            "return ViewingPolicy(allowed_library_ids=[])",
            "return content_policy.ViewingPolicy(allowed_library_ids=[])",
            "return profile.viewing_policy()",
            "async def find_for_profile(self, profile_id: ProfileId) -> ViewingPolicy:\n    pass",
            "assert isinstance(policy, ViewingPolicy)",
        ],
    )
    def test_ignores_deny_all_and_derivation(self, snippet):
        assert not _find_policy_constructions(snippet)

    _METHOD = "async def find_for_profile(self, profile_id):\n"

    def test_accepts_the_adapter_shape(self):
        source = (
            self._METHOD + "    if profile is None:\n"
            "        return ViewingPolicy(allowed_library_ids=[])\n"
            "    return profile.viewing_policy()\n"
        )

        assert not _find_non_derived_returns(source)

    @pytest.mark.parametrize(
        "body",
        [
            # The PR 4 drift: derive, then quietly drop the new axis.
            "    return profile.viewing_policy().with_updates(maturity_limit=None)\n",
            "    return profile.viewing_policy().model_copy(update={'maturity_limit': None})\n",
            # Derive, discard, and return something else.
            "    profile.viewing_policy()\n    return build(profile)\n",
            "    return type(p)(allowed_library_ids=profile.allowed_library_ids)\n",
            # Never derives at all.
            "    return ViewingPolicy(allowed_library_ids=[])\n",
            # Derivation with arguments is not the plain derived policy.
            "    return profile.viewing_policy(strict=False)\n",
        ],
    )
    def test_flags_returns_that_are_not_the_derived_policy(self, body):
        assert _find_non_derived_returns(self._METHOD + body)

    def test_flags_a_module_without_the_adapter_method(self):
        assert _find_non_derived_returns("def other():\n    return profile.viewing_policy()\n")
