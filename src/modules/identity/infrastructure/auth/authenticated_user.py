"""Published authenticated-identity contract for cross-BC route guards.

Other bounded contexts' routes gate on Identity's auth dependencies but
should not depend on Identity's ``UserModel`` ORM (ADR-009). This is the
minimal, ORM-free shape those routes receive instead — just the public
id and whether the caller has admin read authority on this session.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUser:
    """The authenticated caller, as exposed across bounded contexts.

    Attributes:
        external_id: Prefixed public user id (``usr_xxx``) — what routes
            forward to use cases as the acting/requesting user.
        is_admin: Whether the caller holds the admin role with admin
            *read* authority on this session: an administrator the
            parental gate suspends reads as ``False`` (ADR-035,
            Amendment 7). It does not reflect write authority — under
            D10 an admin write can need an unlock while reads are
            granted — so never use it to authorize a state change;
            depend on ``authenticated_admin`` for that.
    """

    external_id: str
    is_admin: bool


__all__ = ["AuthenticatedUser"]
