"""User role enumeration."""

from enum import StrEnum


class UserRole(StrEnum):
    """Role assigned to a user.

    Two-tier model for the household-streaming MVP:

    - ``ADMIN`` — full access (manage libraries, users, settings, scans).
    - ``MEMBER`` — regular user (browse, watch, manage own profiles).

    Refactorable to richer RBAC later without changing the BC boundary.
    See ADR-010 (rationale and trade-offs).

    Example:
        >>> UserRole("admin")
        <UserRole.ADMIN: 'admin'>
        >>> UserRole.MEMBER.value
        'member'
    """

    ADMIN = "admin"
    MEMBER = "member"


__all__ = ["UserRole"]
