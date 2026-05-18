"""SQLAlchemy implementation of UserRepository."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.repositories.user_repository import UserRepository
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.persistence.mappers.user_mapper import (
    UserMapper,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.user_id import UserId


class SqlAlchemyUserRepository(UserRepository):
    """Async SQLAlchemy repository for the User aggregate.

    Distinguishes insert vs. update via ``id is None``: a fresh entity
    is fully written; an existing one only gets its domain-mutable
    fields touched (``role``, ``is_active``) so FastAPI Users-owned
    fields stay intact. Transaction commit is the UoW's responsibility.
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
            UserModel.email == email.value,
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
        stmt = select(func.count(UserModel.id)).where(UserModel.deleted_at.is_(None))
        if role is not None:
            stmt = stmt.where(UserModel.role == role.value)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_active_admins(self) -> int:
        """Count non-deleted, active users in the ``ADMIN`` role."""
        stmt = select(func.count(UserModel.id)).where(
            UserModel.deleted_at.is_(None),
            UserModel.is_active.is_(True),
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
