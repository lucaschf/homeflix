"""Tests for PromoteMovieToSeriesUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.building_blocks.application.event_bus import EventBus
from src.modules.media.application.dtos.admin_relink_dtos import (
    PromoteMovieToSeriesInput,
)
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaOutput
from src.modules.media.application.ports import (
    EpisodeMetadata,
    MediaMetadata,
    MetadataProvider,
    SeasonMetadata,
)
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)
from src.modules.media.application.use_cases.promote_movie_to_series import (
    PromoteMovieToSeriesUseCase,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.events import MoviePromotedToSeriesEvent
from src.modules.media.domain.value_objects import MovieId
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_movie() -> Movie:
    return Movie.create(
        library_id=_LIBRARY_ID,
        title="Salem's Lot",
        year=1979,
        duration=11400,
        file_path="/movies/salem.mkv",
        file_size=4_000_000_000,
        resolution="1080p",
    )


def _series_meta(episodes: int = 2) -> MediaMetadata:
    """Build a TMDB series metadata stub with ``episodes`` episodes."""
    return MediaMetadata(
        title="Salem's Lot",
        year=1979,
        tmdb_id=16118,
        seasons=[
            SeasonMetadata(
                season_number=1,
                episodes=[
                    EpisodeMetadata(season_number=1, episode_number=i + 1, title=f"Part {i + 1}")
                    for i in range(episodes)
                ],
            )
        ],
    )


@pytest.mark.unit
class TestPromoteMovieToSeries:
    @pytest.mark.asyncio
    async def test_should_build_series_with_n_episodes_and_move_files_to_first(self) -> None:
        movie = _make_movie()
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = movie
        mocks.movies.save.side_effect = lambda m: m
        mocks.movies.transfer_file_variants_to_episode = AsyncMock(return_value=1)
        mocks.series.save.side_effect = lambda s: s

        provider = AsyncMock(spec=MetadataProvider)
        provider.get_series_by_id.return_value = _series_meta(episodes=2)

        enrich = AsyncMock(spec=EnrichSeriesMetadataUseCase)
        enrich.execute.return_value = EnrichMediaOutput(
            media_id="ser_placeholder",
            enriched=True,
            provider="tmdb",
        )

        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()

        use_case = PromoteMovieToSeriesUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
            enrich_series_use_case=enrich,
            event_bus=bus,
        )

        output = await use_case.execute(
            PromoteMovieToSeriesInput(movie_id=str(movie.id), tmdb_id=16118),
        )

        assert output.episodes_created == 2
        assert output.movie_id == str(movie.id)
        assert output.series_id.startswith("ser_")
        assert output.first_episode_id.startswith("epi_")

        # File variants moved (one mock call with the picked episode id).
        mocks.movies.transfer_file_variants_to_episode.assert_awaited_once()
        # Source movie soft-deleted.
        mocks.movies.delete.assert_awaited_once()
        # Cross-BC event published with the new ids.
        bus.publish.assert_awaited_once()
        event = bus.publish.await_args.args[0]
        assert isinstance(event, MoviePromotedToSeriesEvent)
        assert event.movie_id == str(movie.id)
        assert event.series_id == output.series_id
        assert event.first_episode_id == output.first_episode_id
        # Re-enrich was triggered with force=True.
        enrich.execute.assert_awaited_once()
        enrich_input = enrich.execute.await_args.args[0]
        assert enrich_input.force is True
        assert enrich_input.media_id == output.series_id

    @pytest.mark.asyncio
    async def test_should_create_placeholder_episode_when_tmdb_has_no_episodes(self) -> None:
        """TMDB sometimes returns a series with empty episode list (rare
        edge case). The promote must still create an episode so the
        movie's file has somewhere to land."""
        movie = _make_movie()
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = movie
        mocks.movies.save.side_effect = lambda m: m
        mocks.movies.transfer_file_variants_to_episode = AsyncMock(return_value=1)
        mocks.series.save.side_effect = lambda s: s

        provider = AsyncMock(spec=MetadataProvider)
        provider.get_series_by_id.return_value = MediaMetadata(
            title="Salem's Lot",
            year=1979,
            tmdb_id=16118,
            seasons=[],
        )

        enrich = AsyncMock(spec=EnrichSeriesMetadataUseCase)
        enrich.execute.return_value = EnrichMediaOutput(media_id="ser", enriched=True)

        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()

        use_case = PromoteMovieToSeriesUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
            enrich_series_use_case=enrich,
            event_bus=bus,
        )

        output = await use_case.execute(
            PromoteMovieToSeriesInput(movie_id=str(movie.id), tmdb_id=16118),
        )

        assert output.episodes_created == 1

    @pytest.mark.asyncio
    async def test_should_swallow_reenrich_failures_so_structure_survives(self) -> None:
        """Re-enrich is best-effort after the structural conversion
        commits — a transient TMDB outage must not roll the promotion
        back, since the catalog change is already persisted and the
        admin can retry enrich via the existing endpoint."""
        movie = _make_movie()
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = movie
        mocks.movies.save.side_effect = lambda m: m
        mocks.movies.transfer_file_variants_to_episode = AsyncMock(return_value=1)
        mocks.series.save.side_effect = lambda s: s

        provider = AsyncMock(spec=MetadataProvider)
        provider.get_series_by_id.return_value = _series_meta(episodes=1)

        enrich = AsyncMock(spec=EnrichSeriesMetadataUseCase)
        enrich.execute.side_effect = RuntimeError("TMDB timeout")

        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()

        use_case = PromoteMovieToSeriesUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
            enrich_series_use_case=enrich,
            event_bus=bus,
        )

        # Should not raise — promote returns even though enrich threw.
        output = await use_case.execute(
            PromoteMovieToSeriesInput(movie_id=str(movie.id), tmdb_id=16118),
        )

        assert output.episodes_created == 1
        bus.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_raise_when_movie_not_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = None
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_series_by_id.return_value = _series_meta()
        enrich = AsyncMock(spec=EnrichSeriesMetadataUseCase)
        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()

        use_case = PromoteMovieToSeriesUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
            enrich_series_use_case=enrich,
            event_bus=bus,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                PromoteMovieToSeriesInput(movie_id=str(MovieId.generate()), tmdb_id=16118),
            )

        bus.publish.assert_not_awaited()
        enrich.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_raise_when_tmdb_id_is_unknown(self) -> None:
        """If TMDB returns nothing for the picked id, abort before
        touching the catalog — the picker shouldn't surface a stale
        id but defend anyway."""
        mocks = make_media_uow_mock()
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_series_by_id.return_value = None
        enrich = AsyncMock(spec=EnrichSeriesMetadataUseCase)
        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()

        use_case = PromoteMovieToSeriesUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
            enrich_series_use_case=enrich,
            event_bus=bus,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                PromoteMovieToSeriesInput(movie_id=str(MovieId.generate()), tmdb_id=9999999),
            )

        mocks.movies.find_by_id.assert_not_awaited()
        bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_validate_tmdb_id_is_positive(self) -> None:
        mocks = make_media_uow_mock()
        provider = AsyncMock(spec=MetadataProvider)
        enrich = AsyncMock(spec=EnrichSeriesMetadataUseCase)
        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()

        use_case = PromoteMovieToSeriesUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
            enrich_series_use_case=enrich,
            event_bus=bus,
        )

        with pytest.raises(UseCaseValidationException):
            await use_case.execute(
                PromoteMovieToSeriesInput(movie_id=str(MovieId.generate()), tmdb_id=0),
            )

        provider.get_series_by_id.assert_not_awaited()
