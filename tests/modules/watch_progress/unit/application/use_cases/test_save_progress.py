"""Tests for SaveProgressUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.watch_progress.application.dtos import ProgressOutput, SaveProgressInput
from src.modules.watch_progress.application.ports import (
    MediaLookupPort,
    ProfileViewingPolicyPort,
)
from src.modules.watch_progress.application.use_cases import SaveProgressUseCase
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import WatchableMediaId, WatchableMediaType
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.watch_progress.unit.conftest import (
    WatchProgressUoWMocks,
    make_watch_progress_uow_mock,
)

_PROFILE_ID = ProfileId("prf_test12345678")
_POLICY = ViewingPolicy.unrestricted(["lib_test12345678"])
_MOVIE_ID = "mov_abc123def456"
_SERIES_ID = "ser_xyz789abc123"


def _media_lookup(visible: set[str]) -> AsyncMock:
    """Build a media port that reports ``visible`` as the only visible titles."""
    media_lookup = AsyncMock(spec=MediaLookupPort)

    async def find_visible_titles(*, movie_ids, series_ids, policy):
        requested = {m.value for m in movie_ids} | {s.value for s in series_ids}
        return frozenset(requested & visible)

    media_lookup.find_visible_titles.side_effect = find_visible_titles
    return media_lookup


def _policy_port(policy: ViewingPolicy = _POLICY) -> AsyncMock:
    port = AsyncMock(spec=ProfileViewingPolicyPort)
    port.find_for_profile.return_value = policy
    return port


def _make_use_case(
    mocks: WatchProgressUoWMocks,
    *,
    visible: set[str] | None = None,
    policy: ViewingPolicy = _POLICY,
    media_lookup: AsyncMock | None = None,
) -> SaveProgressUseCase:
    return SaveProgressUseCase(
        uow_factory=mocks.factory,
        media_lookup=media_lookup or _media_lookup({_MOVIE_ID} if visible is None else visible),
        profile_viewing_policy=_policy_port(policy),
    )


def _input(media_id: str = _MOVIE_ID, media_type: str = "movie", **overrides) -> SaveProgressInput:
    fields = {
        "profile_id": _PROFILE_ID.value,
        "media_id": media_id,
        "media_type": media_type,
        "position_seconds": 1800,
        "duration_seconds": 7200,
        **overrides,
    }
    return SaveProgressInput(**fields)


class TestSaveProgressUseCase:
    """Tests for SaveProgressUseCase."""

    @pytest.mark.asyncio
    async def test_creates_new_progress_when_none_exists(self):
        mocks = make_watch_progress_uow_mock()
        mock_repo = mocks.progress
        mock_repo.find_by_media_id.return_value = None
        mock_repo.save.side_effect = lambda p: p
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            SaveProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type="movie",
                position_seconds=1800,
                duration_seconds=7200,
            )
        )

        assert isinstance(result, ProgressOutput)
        assert result.media_id == "mov_abc123def456"
        assert result.position_seconds == 1800
        assert result.status == "in_progress"
        mock_repo.save.assert_called_once()
        # The repo find lookup was scoped by profile.
        mock_repo.find_by_media_id.assert_called_once_with(
            WatchableMediaId("mov_abc123def456"), _PROFILE_ID
        )

    @pytest.mark.asyncio
    async def test_updates_existing_progress(self):
        existing = WatchProgress.create(
            profile_id=_PROFILE_ID,
            media_id="mov_abc123def456",
            media_type=WatchableMediaType.MOVIE,
            position_seconds=1000,
            duration_seconds=7200,
        )
        mocks = make_watch_progress_uow_mock()
        mock_repo = mocks.progress
        mock_repo.find_by_media_id.return_value = existing
        mock_repo.save.side_effect = lambda p: p
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            SaveProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type="movie",
                position_seconds=3600,
                duration_seconds=7200,
            )
        )

        assert result.position_seconds == 3600
        assert result.percentage == 50.0

    @pytest.mark.asyncio
    async def test_auto_completes_at_90_percent(self):
        mocks = make_watch_progress_uow_mock()
        mock_repo = mocks.progress
        mock_repo.find_by_media_id.return_value = None
        mock_repo.save.side_effect = lambda p: p
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            SaveProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type="movie",
                position_seconds=6500,
                duration_seconds=7200,
            )
        )

        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_saves_audio_and_subtitle_track(self):
        mocks = make_watch_progress_uow_mock()
        mock_repo = mocks.progress
        mock_repo.find_by_media_id.return_value = None
        mock_repo.save.side_effect = lambda p: p
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            SaveProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type="movie",
                position_seconds=100,
                duration_seconds=7200,
                audio_track=2,
                subtitle_track=1,
            )
        )

        assert result.audio_track == 2
        assert result.subtitle_track == 1

    @pytest.mark.asyncio
    async def test_subtitles_off_round_trips_through_the_use_case(self):
        # The -1 = off sentinel must survive the full wire→VO→entity→wire path.
        mocks = make_watch_progress_uow_mock()
        mock_repo = mocks.progress
        mock_repo.find_by_media_id.return_value = None
        mock_repo.save.side_effect = lambda p: p
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            SaveProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type="movie",
                position_seconds=100,
                duration_seconds=7200,
                subtitle_track=-1,
            )
        )

        assert result.subtitle_track == -1


class TestSaveProgressVisibilityGate:
    """Progress is only recorded on a title the profile can see."""

    @pytest.mark.asyncio
    async def test_visible_movie_output_matches_the_ungated_result(self):
        mocks = make_watch_progress_uow_mock()
        mocks.progress.find_by_media_id.return_value = None
        mocks.progress.save.side_effect = lambda p: p

        result = await _make_use_case(mocks).execute(_input(audio_track=1, subtitle_track=-1))

        assert result.media_id == _MOVIE_ID
        assert result.media_type == WatchableMediaType.MOVIE
        assert result.position_seconds == 1800
        assert result.duration_seconds == 7200
        assert result.percentage == 25.0
        assert result.status == "in_progress"
        assert result.audio_track == 1
        assert result.subtitle_track == -1
        mocks.progress.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deny_all_raises_404_without_media_or_uow(self):
        mocks = make_watch_progress_uow_mock()
        media_lookup = _media_lookup({_MOVIE_ID})
        use_case = _make_use_case(
            mocks,
            policy=ViewingPolicy(allowed_library_ids=[]),
            media_lookup=media_lookup,
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input())

        assert exc_info.value.resource_type == "Movie"
        assert exc_info.value.resource_id == _MOVIE_ID
        media_lookup.find_visible_titles.assert_not_awaited()
        mocks.factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_hidden_movie_raises_404_and_saves_nothing(self):
        mocks = make_watch_progress_uow_mock()
        mocks.progress.find_by_media_id.return_value = None
        media_lookup = _media_lookup(set())
        use_case = _make_use_case(mocks, media_lookup=media_lookup)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input())

        assert (exc_info.value.resource_type, exc_info.value.resource_id) == ("Movie", _MOVIE_ID)
        media_lookup.find_visible_titles.assert_awaited_once_with(
            movie_ids=[MovieId(_MOVIE_ID)], series_ids=[], policy=_POLICY
        )
        mocks.progress.save.assert_not_awaited()
        mocks.factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_episode_is_gated_by_its_series_whatever_the_body_says(self):
        mocks = make_watch_progress_uow_mock()
        media_lookup = _media_lookup(set())
        use_case = _make_use_case(mocks, media_lookup=media_lookup)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input(f"epi_{_SERIES_ID}_1_2", media_type="movie"))

        assert (exc_info.value.resource_type, exc_info.value.resource_id) == ("Series", _SERIES_ID)
        media_lookup.find_visible_titles.assert_awaited_once_with(
            movie_ids=[], series_ids=[SeriesId(_SERIES_ID)], policy=_POLICY
        )
        mocks.progress.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_existing_row_on_hidden_title_still_raises_404(self):
        existing = WatchProgress.create(
            profile_id=_PROFILE_ID,
            media_id=_MOVIE_ID,
            media_type=WatchableMediaType.MOVIE,
            position_seconds=1000,
            duration_seconds=7200,
        )
        mocks = make_watch_progress_uow_mock()
        mocks.progress.find_by_media_id.return_value = existing
        mocks.progress.save.side_effect = lambda p: p
        use_case = _make_use_case(mocks, visible=set())

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(_input(position_seconds=3600))

        mocks.progress.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_and_hidden_titles_raise_the_same_error(self):
        """Out of reach and nonexistent titles answer identically.

        The media port cannot tell them apart either, so this pins the
        use-case side: the refusal is built from the id alone.
        """
        missing_mocks = make_watch_progress_uow_mock()
        hidden_mocks = make_watch_progress_uow_mock()
        missing = _make_use_case(missing_mocks, visible=set())
        hidden = _make_use_case(
            hidden_mocks,
            visible=set(),
            policy=ViewingPolicy.unrestricted(["lib_otherlibrary"]),
        )

        with pytest.raises(ResourceNotFoundException) as missing_error:
            await missing.execute(_input())
        with pytest.raises(ResourceNotFoundException) as hidden_error:
            await hidden.execute(_input())

        for attribute in ("resource_type", "resource_id", "code", "message_code", "message"):
            assert getattr(missing_error.value, attribute) == getattr(hidden_error.value, attribute)
        assert missing_error.value.message_code == "MOVIE_NOT_FOUND"
