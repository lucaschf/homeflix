"""Published authenticated-identity contract for cross-BC route guards.

Other bounded contexts' routes gate on Identity's auth dependencies but
should not depend on Identity's ``UserModel`` ORM (ADR-009). This is the
minimal, ORM-free shape those routes receive instead — just the public
id and the role bit a guard needs.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUser:
    """The authenticated caller, as exposed across bounded contexts.

    Attributes:
        external_id: Prefixed public user id (``usr_xxx``) — what routes
            forward to use cases as the acting/requesting user.
        is_admin: Whether the caller holds the admin role (the same check
            ``authenticated_admin`` enforces before returning).
    """

    external_id: str
    is_admin: bool


__all__ = ["AuthenticatedUser"]
