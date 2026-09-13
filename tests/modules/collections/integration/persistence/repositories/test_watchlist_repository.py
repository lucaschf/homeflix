"""Integration tests for SQLAlchemyWatchlistRepository."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.repositories import WatchlistCursor, WatchlistPage
from src.modules.collections.domain.value_objects import CollectionMediaId, ListId
from src.modules.collections.infrastructure.persistence.models import WatchlistItemModel
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyWatchlistRepository,
)
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

SAMPLE_MOVIE_ID = CollectionMediaId("mov_abc123def456")
_PROFILE_ID = ProfileId("prf_test12345678")
_OTHER_PROFILE_ID = ProfileId("prf_otherprofile")


def _create_item(
    media_id: CollectionMediaId | str = SAMPLE_MOVIE_ID,
    media_type: MediaType = MediaType.MOVIE,
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

    async def test_list_page_should_return_all_items(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_aaaaaaaaaaaa"))
        await repo.add(_create_item(media_id="mov_bbbbbbbbbbbb"))
        await repo.add(_create_item(media_id="mov_cccccccccccc"))

        page = await repo.list_page(_PROFILE_ID, limit=100, after=None)

        assert len(page.items) == 3
        assert page.next_cursor is None

    async def test_list_page_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_kept00000000"))
        await repo.add(_create_item(media_id="mov_removed00000"))
        await repo.remove(CollectionMediaId("mov_removed00000"), _PROFILE_ID)

        page = await repo.list_page(_PROFILE_ID, limit=100, after=None)

        assert [i.media_id.value for i in page.items] == ["mov_kept00000000"]

    async def test_list_page_should_respect_limit(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_aaaaaaaaaaaa"))
        await repo.add(_create_item(media_id="mov_bbbbbbbbbbbb"))
        await repo.add(_create_item(media_id="mov_cccccccccccc"))

        page = await repo.list_page(_PROFILE_ID, limit=2, after=None)

        assert len(page.items) == 2
        assert page.next_cursor is not None

    async def test_list_page_should_isolate_by_profile(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await repo.add(_create_item(media_id="mov_aaaaaaaaaaaa", profile_id=_PROFILE_ID))
        await repo.add(_create_item(media_id="mov_bbbbbbbbbbbb", profile_id=_OTHER_PROFILE_ID))

        owner_view = await repo.list_page(_PROFILE_ID, limit=100, after=None)
        other_view = await repo.list_page(_OTHER_PROFILE_ID, limit=100, after=None)

        assert {i.media_id.value for i in owner_view.items} == {"mov_aaaaaaaaaaaa"}
        assert {i.media_id.value for i in other_view.items} == {"mov_bbbbbbbbbbbb"}

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
            media_type=MediaType.SERIES,
        )

        saved = await repo.add(item)

        assert saved.media_type == MediaType.SERIES

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
            to_media_id=CollectionMediaId("ser_promotedxxxx"),
            to_media_type=MediaType.SERIES,
        )

        assert updated == 2
        for profile in (_PROFILE_ID, _OTHER_PROFILE_ID):
            stale = await repo.find_by_media_id(SAMPLE_MOVIE_ID, profile)
            assert stale is None
            fresh = await repo.find_by_media_id(CollectionMediaId("ser_promotedxxxx"), profile)
            assert fresh is not None
            assert fresh.media_type == MediaType.SERIES

    async def test_rewrite_media_id_should_return_zero_when_nothing_matches(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)

        updated = await repo.rewrite_media_id(
            from_media_id=CollectionMediaId("mov_unknown00000"),
            to_media_id=CollectionMediaId("ser_promotedxxxx"),
            to_media_type=MediaType.SERIES,
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


_T0 = datetime(2026, 9, 13, 10, 0, 0, tzinfo=UTC)


async def _seed_row(
    session: AsyncSession,
    media_id: str,
    added_at: datetime,
    *,
    profile_id: ProfileId = _PROFILE_ID,
    deleted: bool = False,
) -> None:
    """Insert a raw row, so exact timestamps can be stored."""
    session.add(
        WatchlistItemModel(
            external_id=ListId.generate().value,
            profile_id=profile_id.value,
            media_id=media_id,
            media_type="movie",
            added_at=added_at,
            deleted_at=added_at if deleted else None,
        )
    )
    await session.flush()


async def _read_watchlist(
    repo: SQLAlchemyWatchlistRepository, *, limit: int
) -> tuple[list[str], list[WatchlistPage]]:
    """Follow the cursor to the end, returning every item id and every page."""
    ids: list[str] = []
    pages: list[WatchlistPage] = []
    cursor: WatchlistCursor | None = None
    while True:
        page = await repo.list_page(_PROFILE_ID, limit=limit, after=cursor)
        pages.append(page)
        ids.extend(item.media_id.value for item in page.items)
        if page.next_cursor is None:
            return ids, pages
        assert len(pages) < 50, "cursor never reached the end of the watchlist"
        cursor = page.next_cursor


@pytest.mark.integration
class TestWatchlistListPage:
    """Keyset pages over a profile's watchlist."""

    async def test_pages_follow_time_then_media_id_without_gaps_or_repeats(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        tie = _T0 + timedelta(minutes=1)
        await _seed_row(db_session, "mov_aaaaaaaaaaaa", tie)
        await _seed_row(db_session, "mov_cccccccccccc", tie)
        await _seed_row(db_session, "mov_bbbbbbbbbbbb", tie)
        await _seed_row(db_session, "mov_zzzzzzzzzzzz", _T0)
        await _seed_row(db_session, "mov_dddddddddddd", _T0 + timedelta(minutes=2))

        ids, pages = await _read_watchlist(repo, limit=2)

        assert ids == [
            "mov_dddddddddddd",
            "mov_cccccccccccc",
            "mov_bbbbbbbbbbbb",
            "mov_aaaaaaaaaaaa",
            "mov_zzzzzzzzzzzz",
        ]
        assert [len(page.items) for page in pages] == [2, 2, 1]
        # The tie is resumed inside the second page, by media id.
        assert pages[0].next_cursor == WatchlistCursor(
            added_at=tie.replace(tzinfo=None), media_id="mov_cccccccccccc"
        )

    async def test_cursor_is_strictly_after_the_last_row(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await _seed_row(db_session, "mov_bbbbbbbbbbbb", _T0)
        await _seed_row(db_session, "mov_aaaaaaaaaaaa", _T0)

        page = await repo.list_page(
            _PROFILE_ID,
            limit=10,
            after=WatchlistCursor(added_at=_T0.replace(tzinfo=None), media_id="mov_bbbbbbbbbbbb"),
        )

        assert [i.media_id.value for i in page.items] == ["mov_aaaaaaaaaaaa"]
        assert page.next_cursor is None

    async def test_page_skips_deleted_rows_and_other_profiles(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await _seed_row(db_session, "mov_kept00000000", _T0 + timedelta(minutes=3))
        await _seed_row(db_session, "mov_deleted00000", _T0 + timedelta(minutes=2), deleted=True)
        await _seed_row(
            db_session,
            "mov_other0000000",
            _T0 + timedelta(minutes=1),
            profile_id=_OTHER_PROFILE_ID,
        )

        page = await repo.list_page(_PROFILE_ID, limit=10, after=None)

        assert [i.media_id.value for i in page.items] == ["mov_kept00000000"]
        assert page.next_cursor is None

    async def test_full_last_page_is_followed_by_an_empty_final_page(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchlistRepository(db_session)
        await _seed_row(db_session, "mov_aaaaaaaaaaaa", _T0 + timedelta(minutes=1))
        await _seed_row(db_session, "mov_bbbbbbbbbbbb", _T0)

        ids, pages = await _read_watchlist(repo, limit=2)

        assert ids == ["mov_aaaaaaaaaaaa", "mov_bbbbbbbbbbbb"]
        assert pages[0].next_cursor == WatchlistCursor(
            added_at=_T0.replace(tzinfo=None), media_id="mov_bbbbbbbbbbbb"
        )
        assert pages[1] == WatchlistPage(items=[], next_cursor=None)

    async def test_microsecond_apart_timestamps_keep_the_stored_order(
        self, db_session: AsyncSession
    ) -> None:
        """The bound cursor must compare like the 26-character text SQLite stores."""
        repo = SQLAlchemyWatchlistRepository(db_session)
        second_boundary = datetime(2026, 9, 13, 10, 0, 1, tzinfo=UTC)
        stamps = {
            "mov_aaaaaaaaaaaa": second_boundary - timedelta(microseconds=2),
            "mov_bbbbbbbbbbbb": second_boundary - timedelta(microseconds=1),
            "mov_cccccccccccc": second_boundary,
            "mov_dddddddddddd": second_boundary + timedelta(microseconds=1),
            "mov_eeeeeeeeeeee": second_boundary + timedelta(microseconds=10),
        }
        # Inserted out of order, so storage order cannot stand in for sorting.
        for media_id in ("mov_cccccccccccc", "mov_eeeeeeeeeeee", "mov_aaaaaaaaaaaa"):
            await _seed_row(db_session, media_id, stamps[media_id])
        for media_id in ("mov_dddddddddddd", "mov_bbbbbbbbbbbb"):
            await _seed_row(db_session, media_id, stamps[media_id])

        stored = (
            await db_session.execute(
                text(f"SELECT added_at FROM {WatchlistItemModel.__table__.name}")
            )
        ).scalars()
        ids, pages = await _read_watchlist(repo, limit=1)

        assert sorted(len(value) for value in stored) == [26] * len(stamps)
        assert ids == [
            "mov_eeeeeeeeeeee",
            "mov_dddddddddddd",
            "mov_cccccccccccc",
            "mov_bbbbbbbbbbbb",
            "mov_aaaaaaaaaaaa",
        ]
        assert len(pages) == len(stamps) + 1
