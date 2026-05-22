"""SQLAlchemy implementation of :class:`SettingRepository`."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.repositories import SettingRepository
from src.modules.settings.domain.value_objects import SettingKey
from src.modules.settings.infrastructure.persistence.mappers import SettingMapper
from src.modules.settings.infrastructure.persistence.models import SettingModel


class SQLAlchemySettingRepository(SettingRepository):
    """SQLAlchemy implementation of :class:`SettingRepository`.

    Backs the ``app_settings`` table introduced by ADR-013. The table
    has at most one row per :class:`SettingKey`, so ``list_all`` reads
    the entire table without pagination.

    Example:
        >>> repo = SQLAlchemySettingRepository(session)
        >>> rows = await repo.list_all()
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self._session = session

    async def list_all(self) -> Sequence[Setting]:
        """Return every persisted setting row."""
        stmt = select(SettingModel)
        result = await self._session.execute(stmt)
        return [SettingMapper.to_entity(m) for m in result.scalars().all()]

    async def find_by_key(self, key: SettingKey) -> Setting | None:
        """Return the row for ``key`` or ``None`` if absent."""
        stmt = select(SettingModel).where(SettingModel.key == key.value)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else SettingMapper.to_entity(model)

    async def upsert(self, setting: Setting) -> Setting:
        """Insert ``setting`` or replace the row with the same key."""
        stmt = select(SettingModel).where(SettingModel.key == setting.id.value)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            model = SettingMapper.to_model(setting)
            self._session.add(model)
        else:
            SettingMapper.update_model(model, setting)

        await self._session.flush()
        await self._session.refresh(model)
        return SettingMapper.to_entity(model)


__all__ = ["SQLAlchemySettingRepository"]
