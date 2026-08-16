"""DefineEpisodeSegmentsUseCase — map episodes onto sub-ranges of one file.

Some mini-series ship several episodes concatenated in a single physical
file. This admin use case attaches a segmented :class:`MediaFile` (ADR-030)
to each existing episode of a season so every episode plays just its window
of the shared file, without splitting the file on disk.
"""

import asyncio
from pathlib import Path

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.modules.media.application.dtos.segment_dtos import (
    AssignedSegmentOutput,
    DefineEpisodeSegmentsInput,
    DefineEpisodeSegmentsOutput,
    EpisodeSegmentSpec,
)
from src.modules.media.application.ports.media_probe_port import MediaProbePort
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    FileSegment,
    MediaFile,
    Resolution,
    SeriesId,
)


class DefineEpisodeSegmentsUseCase:
    """Assign disjoint file segments to a season's episodes (ADR-030).

    The shared file is probed once for resolution and tracks; every episode
    receives a primary :class:`MediaFile` pointing at that same path, bounded
    by its own :class:`FileSegment`, and its duration is set to the segment
    length so intro/credits markers stay episode-relative.

    Example:
        >>> use_case = DefineEpisodeSegmentsUseCase(uow_factory, probe_service)
        >>> await use_case.execute(DefineEpisodeSegmentsInput(
        ...     series_id="ser_abc123abc123",
        ...     season_number=1,
        ...     file_path="/series/mini/whole.mkv",
        ...     segments=[
        ...         EpisodeSegmentSpec(1, 0, 4740),
        ...         EpisodeSegmentSpec(2, 4740, 9480),
        ...     ],
        ... ))
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        probe_service: MediaProbePort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
            probe_service: Probe port used to read the shared file's
                resolution and audio/subtitle tracks.
        """
        self._uow_factory = uow_factory
        self._probe = probe_service

    async def execute(
        self,
        input_dto: DefineEpisodeSegmentsInput,
    ) -> DefineEpisodeSegmentsOutput:
        """Attach a segmented MediaFile to each targeted episode.

        Args:
            input_dto: Series/season, shared file path, and per-episode
                segment specs.

        Returns:
            The episodes updated, in ascending start order.

        Raises:
            UseCaseValidationException: If the segment set is empty,
                contains duplicate episodes, overlaps, or runs past the
                probed file duration.
            ResourceNotFoundException: If the file, series, season, or a
                referenced episode does not exist.
        """
        if not input_dto.segments:
            raise UseCaseValidationException.required_field("segments")

        source = Path(input_dto.file_path)
        if not source.is_file():
            raise ResourceNotFoundException.for_resource("MediaFile", input_dto.file_path)
        file_size = source.stat().st_size

        probed = await asyncio.to_thread(self._probe.probe, input_dto.file_path)
        resolution = Resolution(probed.resolution) if probed.resolution else Resolution.unknown()

        # Process in ascending start order so overlap validation is a single
        # forward scan and the output reads top-to-bottom through the file.
        specs = sorted(input_dto.segments, key=lambda s: s.start_seconds)
        self._validate_segment_set(specs, probed.duration_seconds)

        file_path = FilePath(input_dto.file_path)

        async with self._uow_factory() as uow:
            series = await uow.series.find_by_id(SeriesId(input_dto.series_id))
            if series is None:
                raise ResourceNotFoundException.for_resource("Series", input_dto.series_id)

            season = series.get_season(input_dto.season_number)
            if season is None:
                raise ResourceNotFoundException.for_resource("Season", str(input_dto.season_number))

            assigned: list[AssignedSegmentOutput] = []
            for spec in specs:
                episode = season.get_episode(spec.episode_number)
                if episode is None:
                    raise ResourceNotFoundException.for_resource(
                        "Episode",
                        f"S{input_dto.season_number}E{spec.episode_number}",
                    )

                segment = FileSegment(
                    start_seconds=spec.start_seconds,
                    end_seconds=spec.end_seconds,
                )
                media_file = MediaFile(
                    file_path=file_path,
                    file_size=file_size,
                    resolution=resolution,
                    audio_tracks=list(probed.audio_tracks),
                    subtitle_tracks=list(probed.all_subtitles),
                    is_primary=True,
                    segment=segment,
                )
                episode = episode.with_updates(
                    files=[media_file],
                    duration=Duration(segment.duration_seconds),
                )
                season = season.with_episode_upserted(episode)
                assigned.append(
                    AssignedSegmentOutput(
                        episode_id=str(episode.id) if episode.id else None,
                        episode_number=spec.episode_number,
                        title=episode.get_title(),
                        start_seconds=segment.start_seconds,
                        end_seconds=segment.end_seconds,
                        duration_seconds=segment.duration_seconds,
                    )
                )

            series = series.with_season_upserted(season)
            await uow.series.save(series)

        return DefineEpisodeSegmentsOutput(
            series_id=input_dto.series_id,
            season_number=input_dto.season_number,
            file_path=input_dto.file_path,
            episodes=assigned,
        )

    @staticmethod
    def _validate_segment_set(
        specs: list[EpisodeSegmentSpec],
        file_duration: int | None,
    ) -> None:
        """Reject duplicate, overlapping, or out-of-bounds segment sets.

        Per-segment ordering (``end > start``) is enforced by the
        :class:`FileSegment` value object; this guards the cross-segment
        invariants a single VO cannot see.
        """
        seen: set[int] = set()
        prev_end: int | None = None
        for spec in specs:
            if spec.episode_number in seen:
                raise UseCaseValidationException(
                    message=f"Episode {spec.episode_number} appears more than once",
                    message_code="DUPLICATE_EPISODE_SEGMENT",
                )
            seen.add(spec.episode_number)

            if spec.end_seconds <= spec.start_seconds:
                raise UseCaseValidationException(
                    message=(
                        f"Segment for episode {spec.episode_number} must end " f"after it starts"
                    ),
                    message_code="INVALID_FILE_SEGMENT",
                )

            if prev_end is not None and spec.start_seconds < prev_end:
                raise UseCaseValidationException(
                    message="File segments must not overlap",
                    message_code="OVERLAPPING_FILE_SEGMENTS",
                )
            prev_end = spec.end_seconds

            if file_duration is not None and spec.end_seconds > file_duration:
                raise UseCaseValidationException(
                    message=(
                        f"Segment end {spec.end_seconds}s exceeds file "
                        f"duration {file_duration}s"
                    ),
                    message_code="SEGMENT_EXCEEDS_FILE_DURATION",
                )


__all__ = ["DefineEpisodeSegmentsUseCase"]
