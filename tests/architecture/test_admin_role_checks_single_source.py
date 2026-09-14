"""Admin authority is only ever decided by the parental-gated guards.

Once an account has a parental PIN, holding the ``admin`` role is not the
same as holding admin authority: ``current_admin_user`` and
``authenticated_user`` ask the parental gate too (ADR-035, Amendment 7). A
route that checks ``user.role == UserRole.ADMIN.value`` by hand would skip
that gate and reopen every admin route under a child's profile, and nothing
else would notice: ``test_route_authentication.py`` only sees declared
dependencies, never a check written inside a handler or a helper.

This test parses every module under ``src/`` and fails on any comparison
that reads a ``.role`` attribute against ``UserRole.ADMIN`` (or its value,
or the literal ``"admin"``) outside the allowlist below, where each entry
says why that check is not a route guard. The count per function is pinned,
so a second check added next to an allowed one fails too.

This is a guardrail on source shapes, not a proof: a role read through a
bare variable (``role = user.role``), ``getattr`` or a helper that returns
the role is invisible to it.
"""

import ast
from collections import Counter
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"

_IDENTITY = "src/modules/identity"

#: ``(module path, enclosing function)`` -> how many role/admin comparisons it
#: holds, and why each is allowed.
_ALLOWED: dict[tuple[str, str], tuple[int, str]] = {
    (f"{_IDENTITY}/infrastructure/auth/fastapi_users.py", "current_admin_user"): (
        1,
        "The admin route guard itself: the role check runs before the parental gate, "
        "so a member costs no query and learns nothing about the PIN.",
    ),
    (f"{_IDENTITY}/infrastructure/auth/fastapi_users.py", "authenticated_user"): (
        1,
        "Decides whether to consult the parental gate before reporting is_admin; the "
        "flag is True only when the gate grants admin read authority.",
    ),
    (f"{_IDENTITY}/application/use_cases/get_admin_access.py", "GetAdminAccessUseCase.execute"): (
        1,
        "The admin-access decision the guards and /users/me share: no admin role is "
        "'none', before the parental gate is applied.",
    ),
    (f"{_IDENTITY}/domain/services/admin_quorum.py", "AdminQuorum.ensure_can_remove_admin"): (
        1,
        "Last-admin invariant: counts who holds the role, grants nothing.",
    ),
    (
        f"{_IDENTITY}/application/use_cases/update_user_role.py",
        "UpdateUserRoleUseCase.execute",
    ): (
        1,
        "Reads the target account's current role to apply the last-admin rule on a "
        "demotion; the caller was already gated by current_admin_user.",
    ),
    (
        f"{_IDENTITY}/application/use_cases/delete_admin_user.py",
        "DeleteAdminUserUseCase.execute",
    ): (
        1,
        "Reads the target account's role to apply the last-admin rule on a delete; "
        "the caller was already gated by current_admin_user.",
    ),
    (
        f"{_IDENTITY}/infrastructure/persistence/repositories/sqlalchemy_user_repository.py",
        "SqlAlchemyUserRepository.count_active_admins",
    ): (
        1,
        "SQL filter counting active admins for the last-admin invariant.",
    ),
}


def _reads_role(node: ast.AST) -> bool:
    return any(isinstance(sub, ast.Attribute) and sub.attr == "role" for sub in ast.walk(node))


def _names_admin(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and sub.value == "admin":
            return True
        if (
            isinstance(sub, ast.Attribute)
            and sub.attr == "ADMIN"
            and isinstance(sub.value, ast.Name)
            and sub.value.id == "UserRole"
        ):
            return True
    return False


class _RoleChecks(ast.NodeVisitor):
    """Collect the enclosing function of every role-versus-admin comparison."""

    def __init__(self) -> None:
        self._scope: list[str] = []
        self.found: list[tuple[str, int, str]] = []

    def _enter(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_FunctionDef = _enter
    visit_AsyncFunctionDef = _enter
    visit_ClassDef = _enter

    def visit_Compare(self, node: ast.Compare) -> None:
        operands = [node.left, *node.comparators]
        for i, operand in enumerate(operands):
            others = operands[:i] + operands[i + 1 :]
            if _reads_role(operand) and any(_names_admin(other) for other in others):
                scope = ".".join(self._scope) or "<module>"
                self.found.append((scope, node.lineno, ast.unparse(node)))
                break
        self.generic_visit(node)


def _role_checks(source: str) -> list[tuple[str, int, str]]:
    visitor = _RoleChecks()
    visitor.visit(ast.parse(source))
    return visitor.found


def _scan_src() -> dict[tuple[str, str], list[str]]:
    found: dict[tuple[str, str], list[str]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        module = path.relative_to(_SRC.parent).as_posix()
        for scope, line, code in _role_checks(path.read_text(encoding="utf-8")):
            found.setdefault((module, scope), []).append(f"{module}:{line}: {code}")
    return found


@pytest.fixture(scope="module")
def src_role_checks() -> dict[tuple[str, str], list[str]]:
    return _scan_src()


class TestAdminRoleChecksHaveOneSource:
    def test_no_role_check_outside_the_allowlist(
        self, src_role_checks: dict[tuple[str, str], list[str]]
    ) -> None:
        unexpected = [
            line
            for key, lines in src_role_checks.items()
            if len(lines) > _ALLOWED.get(key, (0, ""))[0]
            for line in lines
        ]

        assert not unexpected, (
            "These comparisons check the admin role outside the parental-gated guards. "
            "Depend on current_admin_user / authenticated_admin instead (required for any "
            "authorization or write); AuthenticatedUser.is_admin from authenticated_user "
            "only shapes a read response:\n" + "\n".join(unexpected)
        )

    def test_allowlist_has_no_stale_entries(
        self, src_role_checks: dict[tuple[str, str], list[str]]
    ) -> None:
        counts = Counter({key: len(lines) for key, lines in src_role_checks.items()})
        stale = [key for key, (expected, _) in _ALLOWED.items() if counts[key] != expected]

        assert not stale, f"Update or drop these allowlist entries: {stale}"


class TestDetector:
    """The rule is only as strong as the comparison shapes it recognizes."""

    @pytest.mark.parametrize(
        "check",
        [
            "user.role == UserRole.ADMIN.value",
            "user.role != UserRole.ADMIN.value",
            "caller.user.role is UserRole.ADMIN",
            "user.role is not UserRole.ADMIN",
            '"admin" == user.role',
            "user.role in (UserRole.ADMIN, UserRole.ADMIN.value)",
            "UserModel.role == UserRole.ADMIN.value",
        ],
    )
    def test_detects_a_hand_written_admin_guard(self, check: str) -> None:
        source = f"""
async def some_route(user=Depends(current_active_user)):
    if {check}:
        return await do_admin_things()
"""

        assert [scope for scope, _, _ in _role_checks(source)] == ["some_route"]

    @pytest.mark.parametrize(
        "check",
        [
            "user.role == UserRole.MEMBER.value",
            "profile.name == 'admin'",
            "new_role is not UserRole.ADMIN",
            "user.is_admin",
        ],
    )
    def test_ignores_comparisons_that_do_not_check_the_admin_role(self, check: str) -> None:
        source = f"""
def helper(user, profile, new_role):
    return {check}
"""

        assert _role_checks(source) == []

    def test_a_guard_added_to_a_route_module_fails_the_scan(self) -> None:
        # The same check as the real guard, pasted into a route handler.
        route = _SRC / "modules/media/presentation/routes/admin_relink_routes.py"
        source = route.read_text(encoding="utf-8") + (
            "\n\nasync def sneaky(user):\n    return user.role == UserRole.ADMIN.value\n"
        )
        module = route.relative_to(_SRC.parent).as_posix()

        found = {(module, scope) for scope, _, _ in _role_checks(source)}

        assert (module, "sneaky") in found
        assert (module, "sneaky") not in _ALLOWED
