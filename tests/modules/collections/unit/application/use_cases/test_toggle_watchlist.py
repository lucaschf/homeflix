"""Tests for ToggleWatchlistUseCase."""

from unittest.mock import AsyncMock, Mock

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_profile_viewing_policy_mock,
    make_visible_titles_lookup_mock,
)
from tests.modules.collections.unit.conftest import CollectionsUoWMocks, make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import (
    ToggleWatchlistInput,
    ToggleWatchlistOutput,
)
from src.modules.collections.application.use_cases import ToggleWatchlistUseCase
from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId
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
) -> ToggleWatchlistUseCase:
    return ToggleWatchlistUseCase(
        uow_factory=mocks.factory,
        media_lookup=media_lookup or make_visible_titles_lookup_mock(_MOVIE_ID, _SERIES_ID),
        profile_viewing_policy=policy_port or make_profile_viewing_policy_mock(_LIBRARY_ID),
    )


def _input(
    media_id: str = _MOVIE_ID, media_type: MediaType = MediaType.MOVIE
) -> ToggleWatchlistInput:
    return ToggleWatchlistInput(
        profile_id=_PROFILE_ID.value, media_id=media_id, media_type=media_type
    )


@pytest.mark.unit
class TestToggleWatchlistUseCase:
    """Tests for toggling watchlist items."""

    @pytest.mark.asyncio
    async def test_should_add_when_not_in_watchlist(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.watchlist
        mock_repo.exists.return_value = False
        mock_repo.add.return_value = WatchlistItem.create(
            profile_id=_PROFILE_ID,
            media_id="mov_abc123def456",
            media_type=MediaType.MOVIE,
        )
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ToggleWatchlistInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            )
        )

        assert isinstance(result, ToggleWatchlistOutput)
        assert result.media_id == "mov_abc123def456"
        assert result.added is True
        mock_repo.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_remove_when_already_in_watchlist(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.watchlist
        mock_repo.exists.return_value = True
        mock_repo.remove.return_value = True
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ToggleWatchlistInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            )
        )

        assert result.added is False
        assert result.media_id == "mov_abc123def456"
        mock_repo.remove.assert_called_once_with(CollectionMediaId("mov_abc123def456"), _PROFILE_ID)

    @pytest.mark.asyncio
    async def test_should_toggle_series(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.watchlist
        mock_repo.exists.return_value = False
        mock_repo.add.return_value = WatchlistItem.create(
            profile_id=_PROFILE_ID,
            media_id="ser_abc123def456",
            media_type=MediaType.SERIES,
        )
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ToggleWatchlistInput(
                profile_id=_PROFILE_ID.value,
                media_id="ser_abc123def456",
                media_type=MediaType.SERIES,
            )
        )

        assert result.added is True


@pytest.mark.unit
class TestToggleWatchlistVisibilityGate:
    """Only a title the profile can see is added; removal is never gated."""

    @pytest.mark.asyncio
    async def test_visible_title_is_added_after_asking_the_catalog_with_the_policy(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = False
        media_lookup = make_visible_titles_lookup_mock(_MOVIE_ID)
        policy_port = make_profile_viewing_policy_mock(_LIBRARY_ID)

        result = await _make_use_case(
            mocks, media_lookup=media_lookup, policy_port=policy_port
        ).execute(_input())

        assert result == ToggleWatchlistOutput(media_id=_MOVIE_ID, added=True)
        policy_port.find_for_profile.assert_awaited_once_with(_PROFILE_ID)
        media_lookup.find_visible_titles.assert_awaited_once_with(
            movie_ids=[MovieId(_MOVIE_ID)],
            series_ids=[],
            policy=ViewingPolicy(allowed_library_ids=[_LIBRARY_ID]),
        )
        added = mocks.watchlist.add.await_args.args[0]
        assert (added.profile_id, added.media_id, added.media_type) == (
            _PROFILE_ID,
            CollectionMediaId(_MOVIE_ID),
            MediaType.MOVIE,
        )

    @pytest.mark.asyncio
    async def test_absent_hidden_title_raises_404_and_adds_nothing(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = False
        use_case = _make_use_case(mocks, media_lookup=make_visible_titles_lookup_mock())

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input())

        assert (exc_info.value.resource_type, exc_info.value.resource_id) == ("Movie", _MOVIE_ID)
        mocks.watchlist.add.assert_not_awaited()
        mocks.watchlist.remove.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_present_hidden_title_is_still_removed(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = True
        use_case = _make_use_case(mocks, media_lookup=make_visible_titles_lookup_mock())

        result = await use_case.execute(_input())

        assert result == ToggleWatchlistOutput(media_id=_MOVIE_ID, added=False)
        mocks.watchlist.remove.assert_awaited_once_with(CollectionMediaId(_MOVIE_ID), _PROFILE_ID)
        mocks.watchlist.add.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deny_all_absent_raises_404_without_asking_the_catalog(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = False
        media_lookup = make_visible_titles_lookup_mock(_MOVIE_ID)
        use_case = _make_use_case(
            mocks, media_lookup=media_lookup, policy_port=make_profile_viewing_policy_mock()
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input())

        assert (exc_info.value.resource_type, exc_info.value.resource_id) == ("Movie", _MOVIE_ID)
        media_lookup.find_visible_titles.assert_not_awaited()
        mocks.watchlist.add.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deny_all_present_is_still_removed(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = True
        media_lookup = make_visible_titles_lookup_mock(_MOVIE_ID)
        use_case = _make_use_case(
            mocks, media_lookup=media_lookup, policy_port=make_profile_viewing_policy_mock()
        )

        result = await use_case.execute(_input())

        assert result.added is False
        mocks.watchlist.remove.assert_awaited_once_with(CollectionMediaId(_MOVIE_ID), _PROFILE_ID)
        media_lookup.find_visible_titles.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refusal_takes_the_type_from_the_id_prefix_not_the_body(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = False
        media_lookup = make_visible_titles_lookup_mock()
        use_case = _make_use_case(mocks, media_lookup=media_lookup)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input(_SERIES_ID, media_type=MediaType.MOVIE))

        assert (exc_info.value.resource_type, exc_info.value.resource_id) == ("Series", _SERIES_ID)
        media_lookup.find_visible_titles.assert_awaited_once_with(
            movie_ids=[],
            series_ids=[SeriesId(_SERIES_ID)],
            policy=ViewingPolicy(allowed_library_ids=[_LIBRARY_ID]),
        )
        mocks.watchlist.add.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_policy_and_visibility_are_read_before_the_watchlist_transaction(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = False
        media_lookup = make_visible_titles_lookup_mock(_MOVIE_ID)
        policy_port = make_profile_viewing_policy_mock(_LIBRARY_ID)
        manager = Mock()
        manager.attach_mock(policy_port.find_for_profile, "policy")
        manager.attach_mock(media_lookup.find_visible_titles, "visibility")
        manager.attach_mock(mocks.factory, "uow")

        await _make_use_case(mocks, media_lookup=media_lookup, policy_port=policy_port).execute(
            _input()
        )

        order = [
            name for name, _, _ in manager.mock_calls if name in {"policy", "visibility", "uow"}
        ]
        assert order == ["policy", "visibility", "uow"]

    @pytest.mark.asyncio
    async def test_missing_out_of_reach_and_above_limit_raise_the_same_error(self) -> None:
        """The refusal is built from the id alone, whatever hid the title."""
        policies = {
            "missing": ViewingPolicy(allowed_library_ids=[_LIBRARY_ID]),
            "other_library": ViewingPolicy(allowed_library_ids=["lib_otherlibrary"]),
            "above_limit": ViewingPolicy(
                allowed_library_ids=[_LIBRARY_ID], maturity_limit=AgeRating(12)
            ),
        }
        errors: dict[str, ResourceNotFoundException] = {}
        for case, policy in policies.items():
            mocks = make_collections_uow_mock()
            mocks.watchlist.exists.return_value = False
            policy_port = make_profile_viewing_policy_mock()
            policy_port.find_for_profile.return_value = policy
            use_case = _make_use_case(
                mocks, media_lookup=make_visible_titles_lookup_mock(), policy_port=policy_port
            )
            with pytest.raises(ResourceNotFoundException) as exc_info:
                await use_case.execute(_input())
            errors[case] = exc_info.value

        attributes = ("resource_type", "resource_id", "code", "message_code", "message", "details")
        reference = errors["missing"]
        for error in errors.values():
            for attribute in attributes:
                assert getattr(error, attribute) == getattr(reference, attribute)
        assert reference.message_code == "MOVIE_NOT_FOUND"
