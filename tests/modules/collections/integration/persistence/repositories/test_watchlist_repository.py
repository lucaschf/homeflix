"""Integration tests for SQLAlchemyWatchlistRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyWatchlistRepository,
)
from src.shared_kernel.value_objects import CollectionMediaType

SAMPLE_MOVIE_ID = "mov_abc123def456"


def _create_item(
    media_id: str = SAMPLE_MOVIE_ID,
    media_type: CollectionMediaType = CollectionMediaType.MOVIE,
) -> WatchlistItem:
    return WatchlistItem.create(media_id=media_id, media_type=media_type)


@pytest.mark.integration
class TestSQLAlchemyWatchlistRepository:
    """Integration tests for watchlist repository."""

    async def test_add_should_persist_item(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        item = _create_item()

        saved = await repo.add(item)

        assert saved.media_id == item.media_id
        assert saved.media_type == item.media_type

    async def test_find_by_media_id_should_return_item(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        item = _create_item(media_id=SAMPLE_MOVIE_ID)
        await repo.add(item)

        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID)

        assert found is not None
        assert found.media_id == SAMPLE_MOVIE_ID

    async def test_find_by_media_id_should_return_none_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)

        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID)

        assert found is None

    async def test_remove_should_soft_delete(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))

        removed = await repo.remove(SAMPLE_MOVIE_ID)

        assert removed is True
        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID)
        assert found is None

    async def test_remove_should_return_false_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)

        removed = await repo.remove(SAMPLE_MOVIE_ID)

        assert removed is False

    async def test_exists_should_return_true_when_present(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))

        exists = await repo.exists(SAMPLE_MOVIE_ID)

        assert exists is True

    async def test_exists_should_return_false_when_absent(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)

        exists = await repo.exists(SAMPLE_MOVIE_ID)

        assert exists is False

    async def test_exists_should_return_false_after_soft_delete(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))
        await repo.remove(SAMPLE_MOVIE_ID)

        exists = await repo.exists(SAMPLE_MOVIE_ID)

        assert exists is False

    async def test_list_all_should_return_all_items(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_aaaaaaaaaaaa"))
        await repo.add(_create_item(media_id="mov_bbbbbbbbbbbb"))
        await repo.add(_create_item(media_id="mov_cccccccccccc"))

        result = await repo.list_all()

        assert len(result) == 3

    async def test_list_all_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_kept000000000"))
        await repo.add(_create_item(media_id="mov_removed00000"))
        await repo.remove("mov_removed00000")

        result = await repo.list_all()

        assert len(result) == 1
        assert result[0].media_id == "mov_kept000000000"

    async def test_list_all_should_respect_limit(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_aaaaaaaaaaaa"))
        await repo.add(_create_item(media_id="mov_bbbbbbbbbbbb"))
        await repo.add(_create_item(media_id="mov_cccccccccccc"))

        result = await repo.list_all(limit=2)

        assert len(result) == 2

    async def test_add_should_restore_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))
        await repo.remove(SAMPLE_MOVIE_ID)

        # Re-add the same media_id
        restored = await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))

        assert restored.media_id == SAMPLE_MOVIE_ID
        # Should be findable again
        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID)
        assert found is not None

    async def test_should_handle_series_type(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        item = _create_item(
            media_id="ser_abc123def456",
            media_type=CollectionMediaType.SERIES,
        )

        saved = await repo.add(item)

        assert saved.media_type == CollectionMediaType.SERIES
