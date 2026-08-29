"""Tests for DefineEpisodeSegmentsUseCase (ADR-030)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.modules.media.application.dtos.segment_dtos import (
    DefineEpisodeSegmentsInput,
    EpisodeSegmentSpec,
)
from src.modules.media.application.use_cases.define_episode_segments import (
    DefineEpisodeSegmentsUseCase,
)
from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    MediaFile,
    Resolution,
    Title,
)
from src.shared_kernel.media_probe.media_probe_port import ProbeResult
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_series() -> Series:
    """A 2-episode season where E1 has the whole file and E2 has none.

    Mirrors an old mini-series enriched from TMDB (two episodes) whose two
    parts live concatenated in one physical file.
    """
    series = Series.create(
        library_id=_LIBRARY_ID,
        title="20,000 Leagues Under the Sea",
        start_year=1997,
    )
    assert series.id is not None
    season = Season(series_id=series.id, season_number=1)
    e1 = Episode(
        series_id=series.id,
        season_number=1,
        episode_number=1,
        title=Title("Part 1"),
        duration=Duration(9480),
        files=[
            MediaFile(
                file_path=FilePath("/series/mini/whole.mkv"),
                file_size=8_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            ),
        ],
    )
    e2 = Episode(
        series_id=series.id,
        season_number=1,
        episode_number=2,
        title=Title("Part 2"),
        duration=Duration(0),
        files=[],
    )
    season = season.with_episode(e1).with_episode(e2)
    return series.with_season(season)


def _probe_mock(*, duration: int | None = 9480) -> MagicMock:
    probe = MagicMock()
    probe.probe.return_value = ProbeResult(
        audio_tracks=[],
        subtitle_tracks=[],
        resolution="1080p",
        duration_seconds=duration,
    )
    return probe


def _shared_file(tmp_path: Path) -> str:
    path = tmp_path / "whole.mkv"
    path.write_bytes(b"x" * 2048)
    return str(path)


def _input(series_id: str, file_path: str) -> DefineEpisodeSegmentsInput:
    return DefineEpisodeSegmentsInput(
        series_id=series_id,
        season_number=1,
        file_path=file_path,
        segments=[
            EpisodeSegmentSpec(episode_number=1, start_seconds=0, end_seconds=4740),
            EpisodeSegmentSpec(episode_number=2, start_seconds=4740, end_seconds=9480),
        ],
    )


@pytest.mark.unit
class TestDefineEpisodeSegmentsUseCase:
    """Tests for DefineEpisodeSegmentsUseCase."""

    @pytest.mark.asyncio
    async def test_assigns_disjoint_segments_to_each_episode(self, tmp_path: Path) -> None:
        mocks = make_media_uow_mock()
        series = _make_series()
        mocks.series.find_by_id.return_value = series
        file_path = _shared_file(tmp_path)

        use_case = DefineEpisodeSegmentsUseCase(
            uow_factory=mocks.factory,
            probe_service=_probe_mock(),
        )
        output = await use_case.execute(_input(str(series.id), file_path))

        mocks.series.save.assert_awaited_once()
        saved: Series = mocks.series.save.await_args.args[0]
        season = saved.get_season(1)
        e1 = season.get_episode(1)
        e2 = season.get_episode(2)

        # Both episodes now point at the same physical file, disjoint windows.
        assert e1.primary_file.file_path.value == file_path
        assert e2.primary_file.file_path.value == file_path
        assert (e1.primary_file.segment.start_seconds, e1.primary_file.segment.end_seconds) == (
            0,
            4740,
        )
        assert (e2.primary_file.segment.start_seconds, e2.primary_file.segment.end_seconds) == (
            4740,
            9480,
        )
        # Duration follows the segment length (episode-relative markers).
        assert e1.duration.value == 4740
        assert e2.duration.value == 4740

        # Output mirrors the assignment, ascending by start.
        assert [o.episode_number for o in output.episodes] == [1, 2]
        assert output.episodes[0].duration_seconds == 4740

    @pytest.mark.asyncio
    async def test_raises_when_file_missing(self, tmp_path: Path) -> None:
        mocks = make_media_uow_mock()
        use_case = DefineEpisodeSegmentsUseCase(
            uow_factory=mocks.factory,
            probe_service=_probe_mock(),
        )
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(_input("ser_abc123abc123", str(tmp_path / "nope.mkv")))

    @pytest.mark.asyncio
    async def test_raises_when_series_missing(self, tmp_path: Path) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = None
        use_case = DefineEpisodeSegmentsUseCase(
            uow_factory=mocks.factory,
            probe_service=_probe_mock(),
        )
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(_input("ser_abc123abc123", _shared_file(tmp_path)))

    @pytest.mark.asyncio
    async def test_raises_when_episode_missing(self, tmp_path: Path) -> None:
        mocks = make_media_uow_mock()
        series = _make_series()
        mocks.series.find_by_id.return_value = series
        use_case = DefineEpisodeSegmentsUseCase(
            uow_factory=mocks.factory,
            probe_service=_probe_mock(),
        )
        bad = DefineEpisodeSegmentsInput(
            series_id=str(series.id),
            season_number=1,
            file_path=_shared_file(tmp_path),
            segments=[EpisodeSegmentSpec(episode_number=9, start_seconds=0, end_seconds=100)],
        )
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(bad)
        mocks.series.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_overlapping_segments(self, tmp_path: Path) -> None:
        mocks = make_media_uow_mock()
        series = _make_series()
        mocks.series.find_by_id.return_value = series
        use_case = DefineEpisodeSegmentsUseCase(
            uow_factory=mocks.factory,
            probe_service=_probe_mock(),
        )
        overlapping = DefineEpisodeSegmentsInput(
            series_id=str(series.id),
            season_number=1,
            file_path=_shared_file(tmp_path),
            segments=[
                EpisodeSegmentSpec(episode_number=1, start_seconds=0, end_seconds=5000),
                EpisodeSegmentSpec(episode_number=2, start_seconds=4740, end_seconds=9480),
            ],
        )
        with pytest.raises(UseCaseValidationException):
            await use_case.execute(overlapping)
        mocks.series.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_segment_past_file_duration(self, tmp_path: Path) -> None:
        mocks = make_media_uow_mock()
        series = _make_series()
        mocks.series.find_by_id.return_value = series
        use_case = DefineEpisodeSegmentsUseCase(
            uow_factory=mocks.factory,
            probe_service=_probe_mock(duration=5000),
        )
        with pytest.raises(UseCaseValidationException):
            await use_case.execute(_input(str(series.id), _shared_file(tmp_path)))
        mocks.series.save.assert_not_called()
