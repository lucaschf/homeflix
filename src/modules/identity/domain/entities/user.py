"""User aggregate root."""

from __future__ import annotations

from typing import Self

from pydantic import Field

from src.building_blocks.domain.entity import AggregateRoot
from src.modules.identity.domain.value_objects.email import Email  # noqa: TCH001
from src.modules.identity.domain.value_objects.user_id import UserId
from src.modules.identity.domain.value_objects.user_role import UserRole


class User(AggregateRoot[UserId]):
    """Authenticated user of the system.

    Aggregate root for authentication and lifecycle. Profiles are a
    separate aggregate (referenced by ``Profile.user_id``) so that
    auth checks do not pay the cost of hydrating the profile list on
    every request — see ADR-010 framing.

    Attributes:
        id: External user ID (``usr_xxx``). Internally the database
            stores a UUID; the mapping is owned by the SQLAlchemy
            mapper and the UUID never crosses into domain code.
        email: User's email address (used as the login identifier).
        role: Coarse-grained role for authorization gates.
        is_active: Whether the user can log in. Toggled (not deleted) on
            offboarding so historical data remains attributable.
        is_superuser: Mirrors FastAPI Users' ``is_superuser`` field.
            Distinct from ``role == ADMIN``: superuser is a hard
            override used by FastAPI Users' built-in admin routes.
        is_verified: Mirrors FastAPI Users' email-verification flag.
            Defaults to True for users created by the admin CLI; will
            be False for self-service registration once that ships.
        hashed_password: BCrypt hash maintained by FastAPI Users.
            ``None`` is reserved for users who only authenticate via
            OAuth (deferred to a future PR).

    Example:
        >>> user = User.create(email=Email("admin@homeflix.local"),
        ...                    role=UserRole.ADMIN)
        >>> updated = user.with_role(UserRole.MEMBER)
        >>> updated.role
        <UserRole.MEMBER: 'member'>
    """

    id: UserId | None = Field(default=None)
    email: Email
    role: UserRole = UserRole.MEMBER
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False
    hashed_password: str | None = None

    @classmethod
    def create(
        cls,
        email: Email,
        role: UserRole = UserRole.MEMBER,
        *,
        is_superuser: bool = False,
        is_verified: bool = False,
        hashed_password: str | None = None,
    ) -> User:
        """Build a fresh ``User`` (id assigned at persistence time)."""
        return cls(
            email=email,
            role=role,
            is_superuser=is_superuser,
            is_verified=is_verified,
            hashed_password=hashed_password,
        )

    def with_role(self, role: UserRole) -> Self:
        """Return a copy with the given role."""
        return self.with_updates(role=role)

    def with_email(self, email: Email) -> Self:
        """Return a copy with the given email."""
        return self.with_updates(email=email)

    def with_verified(self, *, verified: bool = True) -> Self:
        """Return a copy with the verified flag set."""
        return self.with_updates(is_verified=verified)

    def deactivated(self) -> Self:
        """Return a copy marked as inactive (cannot log in)."""
        return self.with_updates(is_active=False)

    def reactivated(self) -> Self:
        """Return a copy marked as active."""
        return self.with_updates(is_active=True)


__all__ = ["User"]
