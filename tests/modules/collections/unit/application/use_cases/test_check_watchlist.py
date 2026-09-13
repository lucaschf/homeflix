"""Tests for CheckWatchlistUseCase."""

from unittest.mock import AsyncMock

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_profile_viewing_policy_mock,
    make_visible_titles_lookup_mock,
)
from tests.modules.collections.unit.conftest import CollectionsUoWMocks, make_collections_uow_mock

from src.modules.collections.application.dtos import CheckWatchlistInput
from src.modules.collections.application.use_cases import CheckWatchlistUseCase
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.media_id import SeriesId
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")
_LIBRARY_ID = "lib_test12345678"
_MOVIE_ID = "mov_abc123def456"
_SERIES_ID = "ser_abc123def456"


def _make_use_case(
    mocks: CollectionsUoWMocks,
    *,
    media_lookup: AsyncMock | None = None,
    policy_port: AsyncMock | None = None,
) -> CheckWatchlistUseCase:
    return CheckWatchlistUseCase(
        uow_factory=mocks.factory,
        media_lookup=media_lookup or make_visible_titles_lookup_mock(_MOVIE_ID),
        profile_viewing_policy=policy_port or make_profile_viewing_policy_mock(_LIBRARY_ID),
    )


def _input(media_id: str = _MOVIE_ID) -> CheckWatchlistInput:
    return CheckWatchlistInput(profile_id=_PROFILE_ID.value, media_id=media_id)


@pytest.mark.unit
class TestCheckWatchlistUseCase:
    """Tests for checking if a media is in the watchlist."""

    @pytest.mark.asyncio
    async def test_should_return_true_when_in_watchlist(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = True
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            CheckWatchlistInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
            )
        )

        assert result is True
        mocks.watchlist.exists.assert_called_once_with(
            CollectionMediaId("mov_abc123def456"), _PROFILE_ID
        )

    @pytest.mark.asyncio
    async def test_should_return_false_when_not_in_watchlist(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = False
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            CheckWatchlistInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
            )
        )

        assert result is False


@pytest.mark.unit
class TestCheckWatchlistVisibility:
    """An entry on a title the profile cannot see reads as absent."""

    @pytest.mark.asyncio
    async def test_present_hidden_title_reads_as_absent(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = True
        media_lookup = make_visible_titles_lookup_mock()
        policy_port = make_profile_viewing_policy_mock(_LIBRARY_ID)

        result = await _make_use_case(
            mocks, media_lookup=media_lookup, policy_port=policy_port
        ).execute(_input(_SERIES_ID))

        assert result is False
        policy_port.find_for_profile.assert_awaited_once_with(_PROFILE_ID)
        media_lookup.find_visible_titles.assert_awaited_once_with(
            movie_ids=[],
            series_ids=[SeriesId(_SERIES_ID)],
            policy=ViewingPolicy(allowed_library_ids=[_LIBRARY_ID]),
        )

    @pytest.mark.asyncio
    async def test_absent_entry_answers_false_without_asking_identity_or_the_catalog(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = False
        media_lookup = make_visible_titles_lookup_mock(_MOVIE_ID)
        policy_port = make_profile_viewing_policy_mock(_LIBRARY_ID)

        result = await _make_use_case(
            mocks, media_lookup=media_lookup, policy_port=policy_port
        ).execute(_input())

        assert result is False
        policy_port.find_for_profile.assert_not_awaited()
        media_lookup.find_visible_titles.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deny_all_reads_as_absent_without_asking_the_catalog(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = True
        media_lookup = make_visible_titles_lookup_mock(_MOVIE_ID)

        result = await _make_use_case(
            mocks, media_lookup=media_lookup, policy_port=make_profile_viewing_policy_mock()
        ).execute(_input())

        assert result is False
        media_lookup.find_visible_titles.assert_not_awaited()
