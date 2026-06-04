"""Domain service guarding the always-one-active-admin invariant (ADR-017)."""

from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.errors import CannotDemoteLastAdminError
from src.modules.identity.domain.value_objects.user_role import UserRole


class AdminQuorum:
    """Enforces that the system never drops to zero active admins.

    The count of active admins is a repository concern, so the guard
    takes it as input: the use case fetches ``count_active_admins()`` and
    passes it here. Call this on every operation that strips a user's
    admin access — demote-to-member, delete, or deactivate — so the rule
    lives in one place instead of being re-implemented (and diverging)
    per use case (ADR-017).
    """

    @staticmethod
    def ensure_can_remove_admin(user: User, active_admin_count: int) -> None:
        """Reject removing ``user``'s admin access when they are the last one.

        A no-op when ``user`` is not an admin — callers can invoke it
        unconditionally on a remove/demote/deactivate path without first
        checking the role.

        Args:
            user: The user whose admin access is about to be stripped.
            active_admin_count: Current number of active admins,
                including ``user`` when they are one.

        Raises:
            CannotDemoteLastAdminError: When ``user`` is the only active
                admin, which would leave the system with none.
        """
        if user.role is UserRole.ADMIN and active_admin_count <= 1:
            raise CannotDemoteLastAdminError(
                message="Cannot remove the last active admin — promote another user first.",
            )


__all__ = ["AdminQuorum"]
