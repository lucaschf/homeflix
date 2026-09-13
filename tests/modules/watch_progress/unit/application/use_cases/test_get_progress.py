"""Tests for GetProgressUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.modules.watch_progress.application.dtos import GetProgressInput, ProgressOutput
from src.modules.watch_progress.application.ports import (
    MediaLookupPort,
    ProfileViewingPolicyPort,
)
from src.modules.watch_progress.application.use_cases import GetProgressUseCase
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import WatchableMediaId, WatchableMediaType
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.media_id import SeriesId
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.watch_progress.unit.conftest import (
    WatchProgressUoWMocks,
    make_watch_progress_uow_mock,
)

_PROFILE_ID = ProfileId("prf_test12345678")
_POLICY = ViewingPolicy.unrestricted(["lib_test12345678"])


def _existing(media_id: str = "mov_abc123def456") -> WatchProgress:
    return WatchProgress.create(
        profile_id=_PROFILE_ID,
        media_id=media_id,
        media_type=(
            WatchableMediaType.MOVIE if media_id.startswith("mov_") else WatchableMediaType.EPISODE
        ),
        position_seconds=1800,
        duration_seconds=7200,
    )


def _make_use_case(
    mocks: WatchProgressUoWMocks,
    *,
    visible: set[str],
    policy: ViewingPolicy = _POLICY,
) -> tuple[GetProgressUseCase, AsyncMock, AsyncMock]:
    media_lookup = AsyncMock(spec=MediaLookupPort)

    async def find_visible_titles(*, movie_ids, series_ids, policy):
        requested = {m.value for m in movie_ids} | {s.value for s in series_ids}
        return frozenset(requested & visible)

    media_lookup.find_visible_titles.side_effect = find_visible_titles
    policy_port = AsyncMock(spec=ProfileViewingPolicyPort)
    policy_port.find_for_profile.return_value = policy
    use_case = GetProgressUseCase(
        uow_factory=mocks.factory,
        media_lookup=media_lookup,
        profile_viewing_policy=policy_port,
    )
    return use_case, media_lookup, policy_port


class TestGetProgressUseCase:
    """Tests for GetProgressUseCase."""

    @pytest.mark.asyncio
    async def test_returns_progress_when_found(self):
        existing = _existing()
        mocks = make_watch_progress_uow_mock()
        mocks.progress.find_by_media_id.return_value = existing
        use_case, _, policy_port = _make_use_case(mocks, visible={"mov_abc123def456"})

        result = await use_case.execute(
            GetProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
            )
        )

        assert isinstance(result, ProgressOutput)
        assert result == ProgressOutput.from_entity(existing)
        assert result.position_seconds == 1800
        assert result.percentage == 25.0
        mocks.progress.find_by_media_id.assert_called_once_with(
            WatchableMediaId("mov_abc123def456"), _PROFILE_ID
        )
        policy_port.find_for_profile.assert_awaited_once_with(_PROFILE_ID)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        mocks = make_watch_progress_uow_mock()
        mocks.progress.find_by_media_id.return_value = None
        use_case, media_lookup, policy_port = _make_use_case(mocks, visible={"mov_abc123def456"})

        result = await use_case.execute(
            GetProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
            )
        )

        assert result is None
        policy_port.find_for_profile.assert_not_awaited()
        media_lookup.find_visible_titles.assert_not_awaited()


class TestGetProgressVisibilityGate:
    """A row on a title the profile cannot see reads as absent."""

    @pytest.mark.asyncio
    async def test_row_on_hidden_title_returns_none(self):
        mocks = make_watch_progress_uow_mock()
        mocks.progress.find_by_media_id.return_value = _existing()
        use_case, media_lookup, _ = _make_use_case(mocks, visible=set())

        result = await use_case.execute(
            GetProgressInput(profile_id=_PROFILE_ID.value, media_id="mov_abc123def456")
        )

        assert result is None
        media_lookup.find_visible_titles.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_row_under_deny_all_policy_returns_none_without_media(self):
        mocks = make_watch_progress_uow_mock()
        mocks.progress.find_by_media_id.return_value = _existing()
        use_case, media_lookup, _ = _make_use_case(
            mocks,
            visible={"mov_abc123def456"},
            policy=ViewingPolicy(allowed_library_ids=[]),
        )

        result = await use_case.execute(
            GetProgressInput(profile_id=_PROFILE_ID.value, media_id="mov_abc123def456")
        )

        assert result is None
        media_lookup.find_visible_titles.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_episode_row_is_gated_by_its_series(self):
        media_id = "epi_ser_xyz789abc123_1_2"
        mocks = make_watch_progress_uow_mock()
        mocks.progress.find_by_media_id.return_value = _existing(media_id)
        use_case, media_lookup, _ = _make_use_case(mocks, visible={"ser_xyz789abc123"})

        result = await use_case.execute(
            GetProgressInput(profile_id=_PROFILE_ID.value, media_id=media_id)
        )

        assert result is not None
        assert result.media_id == media_id
        media_lookup.find_visible_titles.assert_awaited_once_with(
            movie_ids=[], series_ids=[SeriesId("ser_xyz789abc123")], policy=_POLICY
        )
