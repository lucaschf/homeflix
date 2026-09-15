"""SQLAlchemy implementation of UserRepository."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.repositories.user_repository import UserRepository
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.persistence.mappers.user_mapper import (
    UserMapper,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.user_id import UserId


class SqlAlchemyUserRepository(UserRepository):
    """Async SQLAlchemy repository for the User aggregate.

    Distinguishes insert vs. update via ``id is None``: a fresh entity
    is fully written; an existing one only gets its domain-mutable
    fields touched (``role``, ``is_active``) so FastAPI Users-owned
    fields stay intact. An existing user's ``parental_pin_hash`` is
    written only by ``set_parental_pin_hash`` and
    ``clear_unused_parental_pin_hash``. Transaction commit is the UoW's
    responsibility.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, user: User) -> User:
        """Persist a user (insert when missing, partial update when found).

        Follows the same shape as ``SqlAlchemyLibraryRepository.save``:
        always look the row up by ``external_id`` first; restore a
        soft-deleted row before applying updates; reload via
        ``find_by_id`` so the returned entity carries the
        server-assigned timestamps.
        """
        user = user.with_updates(id=UserId.generate_if_absent(user.id))

        stmt = select(UserModel).where(UserModel.external_id == str(user.id))
        existing = (await self._session.execute(stmt)).scalar_one_or_none()

        if existing is not None and existing.is_deleted:
            existing.restore()

        if existing is not None:
            UserMapper.update_model(existing, user)
            await self._session.flush()
        else:
            model = UserMapper.to_model(user)
            self._session.add(model)
            await self._session.flush()

        if user.id is None:
            raise RuntimeError("User id was not assigned before save")
        saved = await self.find_by_id(user.id)
        if saved is None:
            raise RuntimeError(f"User {user.id} disappeared between flush and reload")
        return saved

    async def set_parental_pin_hash(self, user_id: UserId, hashed: str | None) -> bool:
        """Update only ``parental_pin_hash`` (and ``updated_at``) of a live user.

        A single ``UPDATE ... WHERE deleted_at IS NULL``: the PIN use cases
        check the account password between their read and this write, and
        ``save`` would write their stale entity back — restoring a user
        soft-deleted meanwhile and reverting a concurrent demotion. This
        statement never writes ``role``, ``is_active`` or ``deleted_at``,
        so a concurrent delete wins and is reported as ``False``.
        """
        stmt = (
            update(UserModel)
            .where(
                UserModel.external_id == str(user_id),
                UserModel.deleted_at.is_(None),
            )
            .values(parental_pin_hash=hashed, updated_at=func.now())
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return bool(result.rowcount)  # type: ignore[attr-defined]  # SQLAlchemy DML CursorResult

    async def clear_unused_parental_pin_hash(self, user_id: UserId) -> bool:
        """Clear the PIN hash in one ``UPDATE`` guarded by ``NOT EXISTS`` a live limit.

        ``WHERE external_id = :id AND deleted_at IS NULL AND NOT EXISTS (a
        live profile of this user with a maturity limit)``, ``RETURNING`` the
        row id; ``rowcount`` is ``-1`` with ``RETURNING`` on this stack.
        SQLite admits one writer at a time, so a limit write racing this
        statement either committed before it (the subquery sees the limit)
        or runs after this transaction commits and finds no PIN. Under
        PostgreSQL READ COMMITTED the subquery would not see a limit written
        by a transaction still open, and the two writes would need a row lock
        on the user.
        """
        limited = (
            select(ProfileModel.id)
            .where(
                ProfileModel.user_id == UserModel.id,
                ProfileModel.deleted_at.is_(None),
                ProfileModel.maturity_limit.is_not(None),
            )
            .exists()
        )
        stmt = (
            update(UserModel)
            .where(
                UserModel.external_id == str(user_id),
                UserModel.deleted_at.is_(None),
                ~limited,
            )
            .values(parental_pin_hash=None, updated_at=func.now())
            .returning(UserModel.id)  # type: ignore[call-overload]  # fastapi-users typing
            .execution_options(synchronize_session=False)
        )
        return (await self._session.execute(stmt)).first() is not None

    async def lock_for_parental_change(self, user_id: UserId) -> bool:
        """Lock the live account's row, by dialect, and report whether one was found.

        **SQLite** (what the app runs on, and what the tests pin) has no row
        locks. The statement is a no-op ``UPDATE`` of the row — ``external_id``
        and ``updated_at`` set to themselves, the latter explicitly so the
        column's ``onupdate`` does not fire — ``WHERE external_id = :id AND
        deleted_at IS NULL RETURNING id``. As the transaction's first write it
        takes the database's RESERVED lock, which no other connection can take
        until this transaction ends: every other write, gated or not, waits
        (up to the busy timeout) instead of committing between this
        transaction's reads. A read made before it would not be covered,
        which is why it must be the first statement.

        **PostgreSQL**: ``SELECT id ... FOR UPDATE`` on the same row. Only the
        transactions that take this lock wait for it, which is all the
        operations of the contract; the compare-and-sets of the limit, PIN and
        switch writes stay as defence in depth. Not exercised by the tests.
        """
        live = (UserModel.external_id == str(user_id), UserModel.deleted_at.is_(None))
        stmt: Any
        if self._session.get_bind().dialect.name == "sqlite":
            stmt = (
                update(UserModel)
                .where(*live)
                .values(external_id=UserModel.external_id, updated_at=UserModel.updated_at)
                .returning(UserModel.id)  # type: ignore[call-overload]  # fastapi-users typing
                .execution_options(synchronize_session=False)
            )
        else:
            stmt = select(UserModel.id).where(*live).with_for_update()  # type: ignore[call-overload]  # fastapi-users typing
        return (await self._session.execute(stmt)).first() is not None

    async def find_by_id(self, user_id: UserId) -> User | None:
        """Look up a non-deleted user by external ID."""
        stmt = select(UserModel).where(
            UserModel.external_id == str(user_id),
            UserModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else UserMapper.to_entity(model)

    async def find_by_email(self, email: Email) -> User | None:
        """Look up a non-deleted user by normalised email."""
        # Email VO already lower-cases and trims; no further normalisation needed.
        stmt = select(UserModel).where(
            UserModel.email == email.value,  # type: ignore[arg-type]  # fastapi-users typing
            UserModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else UserMapper.to_entity(model)

    async def list_paginated(
        self,
        *,
        role: UserRole | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[User]:
        """Page through non-deleted users newest-first."""
        stmt = select(UserModel).where(UserModel.deleted_at.is_(None))
        if role is not None:
            stmt = stmt.where(UserModel.role == role.value)
        stmt = stmt.order_by(UserModel.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [UserMapper.to_entity(m) for m in result.scalars().all()]

    async def count(self, *, role: UserRole | None = None) -> int:
        """Count non-deleted users matching the filter."""
        stmt = select(func.count(UserModel.id)).where(UserModel.deleted_at.is_(None))  # type: ignore[arg-type]  # fastapi-users typing
        if role is not None:
            stmt = stmt.where(UserModel.role == role.value)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_active_admins(self) -> int:
        """Count non-deleted, active users in the ``ADMIN`` role."""
        stmt = select(func.count(UserModel.id)).where(  # type: ignore[arg-type]  # fastapi-users typing
            UserModel.deleted_at.is_(None),
            UserModel.is_active.is_(True),  # type: ignore[attr-defined]  # fastapi-users typing
            UserModel.role == UserRole.ADMIN.value,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def soft_delete(self, user_id: UserId) -> bool:
        """Soft-delete a user by external id; idempotent / safe re-call."""
        stmt = select(UserModel).where(
            UserModel.external_id == str(user_id),
            UserModel.deleted_at.is_(None),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return False
        model.soft_delete()
        await self._session.flush()
        return True


__all__ = ["SqlAlchemyUserRepository"]
