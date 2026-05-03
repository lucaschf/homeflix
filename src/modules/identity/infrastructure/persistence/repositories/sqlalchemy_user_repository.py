"""SQLAlchemy implementation of UserRepository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.repositories.user_repository import UserRepository
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_id import UserId
from src.modules.identity.infrastructure.persistence.mappers.user_mapper import (
    UserMapper,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel


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
        """Persist a user (insert when id is missing, partial update otherwise)."""
        is_insert = user.id is None
        user = user.with_updates(id=UserId.generate_if_absent(user.id))

        if is_insert:
            model = UserMapper.to_model(user)
            self._session.add(model)
            await self._session.flush()
        else:
            stmt = select(UserModel).where(UserModel.external_id == str(user.id))
            existing = (await self._session.execute(stmt)).scalar_one_or_none()
            if existing is None:
                # The caller asked us to update a user that doesn't exist;
                # treat it as an insert to keep the contract idempotent.
                model = UserMapper.to_model(user)
                self._session.add(model)
            else:
                if existing.is_deleted:
                    existing.restore()
                UserMapper.update_model(existing, user)
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


__all__ = ["SqlAlchemyUserRepository"]
