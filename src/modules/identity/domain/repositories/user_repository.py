"""User repository interface."""

from abc import ABC, abstractmethod

from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_id import UserId


class UserRepository(ABC):
    """Repository interface for the ``User`` aggregate.

    Note on lifecycle: the user table is also written by FastAPI Users
    via ``SQLAlchemyUserDatabase`` (registration, password reset, email
    verification). This repository covers domain-driven reads and the
    narrow set of fields the domain actually mutates (``role``,
    ``is_active``). It deliberately does NOT expose ``delete()`` —
    accounts are deactivated, not removed (preserves attribution of
    historical data).
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


__all__ = ["UserRepository"]
