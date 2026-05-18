"""User repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.shared_kernel.value_objects.user_id import UserId


class UserRepository(ABC):
    """Repository interface for the ``User`` aggregate.

    The user table is also written by FastAPI Users via
    ``SQLAlchemyUserDatabase`` (registration, password reset, email
    verification). This repository covers domain-driven reads and the
    domain-mutable fields (``role``, ``is_active``), plus the admin
    surface (``list_paginated``, ``count_active_admins``,
    ``soft_delete``) that the ``/api/v1/admin/users`` endpoints
    drive.
    """

    @abstractmethod
    async def save(self, user: User) -> User:
        """Persist a user (create on insert, partial update on existing).

        On insert (``user.id is None``) every domain field is written
        and a fresh ``UserId`` is generated. On update only the
        domain-mutable fields (``role``, ``is_active``) are touched —
        FastAPI Users-owned fields (``hashed_password``,
        ``is_verified``, ``is_superuser``) stay untouched.

        Args:
            user: The user to save.

        Returns:
            The saved user, re-read from the database so callers see
            any server-generated values.
        """
        ...

    @abstractmethod
    async def find_by_id(self, user_id: UserId) -> User | None:
        """Look up a user by their prefixed external ID.

        Args:
            user_id: The user's external ID (``usr_xxx``).

        Returns:
            The user if found and not soft-deleted, ``None`` otherwise.
        """
        ...

    @abstractmethod
    async def find_by_email(self, email: Email) -> User | None:
        """Look up a user by email (case-insensitive via the VO).

        Args:
            email: The normalised email address.

        Returns:
            The user if found, ``None`` otherwise.
        """
        ...

    @abstractmethod
    async def list_paginated(
        self,
        *,
        role: UserRole | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[User]:
        """List non-deleted users, optionally filtered by role.

        Args:
            role: Filter to a single ``UserRole`` or ``None`` for all.
            limit: Page size cap (admin list page is short, default 50).
            offset: Rows to skip from the head of the result.

        Returns:
            Users ordered by ``created_at`` descending (newest first).
        """
        ...

    @abstractmethod
    async def count(self, *, role: UserRole | None = None) -> int:
        """Count non-deleted users, optionally filtered by role.

        Args:
            role: Filter to a single ``UserRole`` or ``None`` for all.

        Returns:
            Number of matching non-deleted rows.
        """
        ...

    @abstractmethod
    async def count_active_admins(self) -> int:
        """Count non-deleted users whose role is ``ADMIN`` and active.

        Drives the "block demoting the last admin" guard on the
        role-update use case: when the count would drop to zero
        after a role flip / delete, the operation is refused.
        """
        ...

    @abstractmethod
    async def soft_delete(self, user_id: UserId) -> bool:
        """Mark the user as deleted (sets ``deleted_at``).

        Idempotent: a row that's already soft-deleted returns
        ``False`` (the caller treats it as "user doesn't exist").

        Args:
            user_id: External user id.

        Returns:
            ``True`` when a row was soft-deleted, ``False`` if not
            found or already gone.
        """
        ...


__all__ = ["UserRepository"]
