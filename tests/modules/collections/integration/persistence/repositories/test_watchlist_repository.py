"""Integration tests for SQLAlchemyWatchlistRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyWatchlistRepository,
)
from src.shared_kernel.value_objects import CollectionMediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

SAMPLE_MOVIE_ID = "mov_abc123def456"
_PROFILE_ID = ProfileId("prf_test12345678")
_OTHER_PROFILE_ID = ProfileId("prf_otherprofile")


def _create_item(
    media_id: str = SAMPLE_MOVIE_ID,
    media_type: CollectionMediaType = CollectionMediaType.MOVIE,
    profile_id: ProfileId = _PROFILE_ID,
) -> WatchlistItem:
    return WatchlistItem.create(profile_id=profile_id, media_id=media_id, media_type=media_type)


@pytest.mark.integration
class TestSQLAlchemyWatchlistRepository:
    """Integration tests for watchlist repository."""

    async def test_add_should_persist_item(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        item = _create_item()

        saved = await repo.add(item)

        assert saved.media_id == item.media_id
        assert saved.media_type == item.media_type
        assert saved.profile_id == _PROFILE_ID

    async def test_find_by_media_id_should_return_item(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        item = _create_item(media_id=SAMPLE_MOVIE_ID)
        await repo.add(item)

        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert found is not None
        assert found.media_id == SAMPLE_MOVIE_ID

    async def test_find_by_media_id_should_return_none_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)

        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert found is None

    async def test_find_by_media_id_should_isolate_by_profile(
        self, db_session: AsyncSession
    ) -> None:
        # Same media on two profiles' watchlists are independent rows.
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item())
        await repo.add(_create_item(profile_id=_OTHER_PROFILE_ID))

        owner_view = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)
        other_view = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _OTHER_PROFILE_ID)

        assert owner_view is not None
        assert other_view is not None
        assert owner_view.profile_id == _PROFILE_ID
        assert other_view.profile_id == _OTHER_PROFILE_ID

    async def test_remove_should_soft_delete(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))

        removed = await repo.remove(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert removed is True
        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)
        assert found is None

    async def test_remove_should_return_false_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)

        removed = await repo.remove(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert removed is False

    async def test_remove_should_not_touch_other_profiles_row(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item())
        await repo.add(_create_item(profile_id=_OTHER_PROFILE_ID))

        await repo.remove(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert (await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)) is None
        assert (await repo.find_by_media_id(SAMPLE_MOVIE_ID, _OTHER_PROFILE_ID)) is not None

    async def test_exists_should_return_true_when_present(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))

        exists = await repo.exists(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert exists is True

    async def test_exists_should_return_false_when_absent(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)

        exists = await repo.exists(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert exists is False

    async def test_exists_should_return_false_after_soft_delete(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))
        await repo.remove(SAMPLE_MOVIE_ID, _PROFILE_ID)

        exists = await repo.exists(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert exists is False

    async def test_exists_should_isolate_by_profile(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(profile_id=_PROFILE_ID))

        assert await repo.exists(SAMPLE_MOVIE_ID, _PROFILE_ID) is True
        assert await repo.exists(SAMPLE_MOVIE_ID, _OTHER_PROFILE_ID) is False

    async def test_list_all_should_return_all_items(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_aaaaaaaaaaaa"))
        await repo.add(_create_item(media_id="mov_bbbbbbbbbbbb"))
        await repo.add(_create_item(media_id="mov_cccccccccccc"))

        result = await repo.list_all(_PROFILE_ID)

        assert len(result) == 3

    async def test_list_all_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_kept000000000"))
        await repo.add(_create_item(media_id="mov_removed00000"))
        await repo.remove("mov_removed00000", _PROFILE_ID)

        result = await repo.list_all(_PROFILE_ID)

        assert len(result) == 1
        assert result[0].media_id == "mov_kept000000000"

    async def test_list_all_should_respect_limit(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_aaaaaaaaaaaa"))
        await repo.add(_create_item(media_id="mov_bbbbbbbbbbbb"))
        await repo.add(_create_item(media_id="mov_cccccccccccc"))

        result = await repo.list_all(_PROFILE_ID, limit=2)

        assert len(result) == 2

    async def test_list_all_should_isolate_by_profile(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_aaaaaaaaaaaa", profile_id=_PROFILE_ID))
        await repo.add(_create_item(media_id="mov_bbbbbbbbbbbb", profile_id=_OTHER_PROFILE_ID))

        owner_view = await repo.list_all(_PROFILE_ID)
        other_view = await repo.list_all(_OTHER_PROFILE_ID)

        assert {i.media_id for i in owner_view} == {"mov_aaaaaaaaaaaa"}
        assert {i.media_id for i in other_view} == {"mov_bbbbbbbbbbbb"}

    async def test_add_should_restore_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))
        await repo.remove(SAMPLE_MOVIE_ID, _PROFILE_ID)

        # Re-add the same media_id
        restored = await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))

        assert restored.media_id == SAMPLE_MOVIE_ID
        # Should be findable again
        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)
        assert found is not None

    async def test_should_handle_series_type(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        item = _create_item(
            media_id="ser_abc123def456",
            media_type=CollectionMediaType.SERIES,
        )

        saved = await repo.add(item)

        assert saved.media_type == CollectionMediaType.SERIES

    async def test_rewrite_media_id_should_repoint_rows_across_profiles(
        self, db_session: AsyncSession
    ) -> None:
        """Driven by the promote-to-series flow — watchlist entries
        on the old movie id move to the new series id without losing
        per-profile presence."""
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID, profile_id=_OTHER_PROFILE_ID))

        updated = await repo.rewrite_media_id(
            from_media_id=SAMPLE_MOVIE_ID,
            to_media_id="ser_promotedxxxx",
            to_media_type="series",
        )

        assert updated == 2
        for profile in (_PROFILE_ID, _OTHER_PROFILE_ID):
            stale = await repo.find_by_media_id(SAMPLE_MOVIE_ID, profile)
            assert stale is None
            fresh = await repo.find_by_media_id("ser_promotedxxxx", profile)
            assert fresh is not None
            assert fresh.media_type == CollectionMediaType.SERIES

    async def test_rewrite_media_id_should_return_zero_when_nothing_matches(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)

        updated = await repo.rewrite_media_id(
            from_media_id="mov_unknown00000",
            to_media_id="ser_promotedxxxx",
            to_media_type="series",
        )

        assert updated == 0

    async def test_delete_all_for_profiles_should_wipe_listed_profiles(
        self, db_session: AsyncSession
    ) -> None:
        """Driven by the user-delete cascade — every watchlist row
        owned by a profile id in the list goes away."""
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID, profile_id=_OTHER_PROFILE_ID))

        deleted = await repo.delete_all_for_profiles([_PROFILE_ID.value])

        assert deleted == 1
        assert await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID) is None
        assert await repo.find_by_media_id(SAMPLE_MOVIE_ID, _OTHER_PROFILE_ID) is not None

    async def test_delete_all_for_profiles_should_noop_on_empty_list(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id=SAMPLE_MOVIE_ID))

        deleted = await repo.delete_all_for_profiles([])

        assert deleted == 0
        assert await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID) is not None
