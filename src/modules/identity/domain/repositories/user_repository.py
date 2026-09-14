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
    domain-mutable fields (``role``, ``is_active``), the narrow
    ``set_parental_pin_hash`` and ``clear_unused_parental_pin_hash``
    writes, the account lock the parental changes serialise on
    (``lock_for_parental_change``), plus the admin surface
    (``list_paginated``, ``count_active_admins``, ``soft_delete``) that
    the ``/api/v1/admin/users`` endpoints drive.
    """

    @abstractmethod
    async def save(self, user: User) -> User:
        """Persist a user (create on insert, partial update on existing).

        On insert (``user.id is None``) every domain field is written
        and a fresh ``UserId`` is generated. On update only the
        domain-mutable fields (``role``, ``is_active``) are touched —
        FastAPI Users-owned fields (``hashed_password``, ``is_verified``,
        ``is_superuser``) stay untouched, and so does
        ``parental_pin_hash``, which only ``set_parental_pin_hash``
        writes on an existing user.

        Args:
            user: The user to save.

        Returns:
            The saved user, re-read from the database so callers see
            any server-generated values.
        """
        ...

    @abstractmethod
    async def set_parental_pin_hash(self, user_id: UserId, hashed: str | None) -> bool:
        """Store or clear the parental PIN hash of a live user, and nothing else.

        Exists because setting or removing the PIN checks the account
        password between reading the user and writing the hash, so the
        read entity can be stale by the time it is written. ``save``
        would write that stale entity back: it restores a soft-deleted
        row and rewrites ``role`` and ``is_active``, silently undoing a
        delete or demotion committed meanwhile. This write touches only
        the PIN hash (and ``updated_at``), never restores a soft-deleted
        user, and reports whether a live user took it.

        Args:
            user_id: The user's external ID (``usr_xxx``).
            hashed: The new PIN hash, or ``None`` to clear the PIN.

        Returns:
            ``True`` when a non-deleted user was updated, ``False`` when
            the user does not exist or is soft-deleted.
        """
        ...

    @abstractmethod
    async def clear_unused_parental_pin_hash(self, user_id: UserId) -> bool:
        """Clear a live user's parental PIN hash unless a profile still has a limit.

        One conditional write, so removing the PIN and setting a limit
        cannot interleave into a limit left without a PIN (ADR-035,
        Amendment 7 D2): the statement clears the hash only while no live
        profile of the account has a maturity limit. Like
        ``set_parental_pin_hash`` it touches only the hash (and
        ``updated_at``) and never restores a soft-deleted user.

        Args:
            user_id: The user's external ID (``usr_xxx``).

        Returns:
            ``True`` when this call cleared the hash of a live user (with or
            without a PIN before); ``False`` when the user does not exist,
            is soft-deleted, or a live profile of theirs has a limit.
        """
        ...

    @abstractmethod
    async def lock_for_parental_change(self, user_id: UserId) -> bool:
        """Lock a live account against other parental changes until the transaction ends.

        The contract of the parental gate (ADR-035, Amendment 7): this is the
        **first statement** of the Unit of Work of every operation the gate
        decides on — switching, creating, updating and deleting a profile —
        and of the write of setting or removing the PIN. Everything such an
        operation reads after it, in the same transaction, stays as read
        until the transaction commits or rolls back, because every other one
        on the account waits here. So two of them never interleave: a gate
        never combines a session read before a concurrent change with
        profiles or a PIN read after it, and never decides on a state that
        changes before its write lands. Called after a read of the same
        transaction, it would not cover what changed before it.

        Writes nothing observable on the account.

        Args:
            user_id: The account's external ID (``usr_xxx``).

        Returns:
            ``True`` when a live account was locked; ``False`` when it does
            not exist or is soft-deleted, which locks nothing.
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
