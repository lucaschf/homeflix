"""Tests for EnrichSeriesMetadataUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaInput
from src.modules.media.application.ports import (
    EpisodeMetadata,
    MediaMetadata,
    MetadataProvider,
    SeasonMetadata,
)
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
    _detect_multi_episode,
)
from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.repositories import SeriesRepository
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    MediaFile,
    Resolution,
    Title,
    TmdbId,
)


def _make_series(**kwargs: object) -> Series:
    series = Series.create(title="Breaking Bad", start_year=2008, **kwargs)
    assert series.id is not None
    season = Season(series_id=series.id, season_number=1)
    episode = Episode(
        series_id=series.id,
        season_number=1,
        episode_number=1,
        title=Title("Episode 1"),
        duration=Duration(0),
        files=[
            MediaFile(
                file_path=FilePath("/series/bb/s01e01.mkv"),
                file_size=500_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            ),
        ],
    )
    season = season.with_episode(episode)
    return series.with_season(season)


def _make_metadata() -> MediaMetadata:
    return MediaMetadata(
        title="Breaking Bad",
        original_title="Breaking Bad",
        year=2008,
        end_year=2013,
        synopsis="A chemistry teacher turns to a life of crime.",
        genres=["Drama", "Crime"],
        tmdb_id=1396,
        imdb_id="tt0903747",
        seasons=[
            SeasonMetadata(
                season_number=1,
                title="Season 1",
                synopsis="The beginning.",
                air_date="2008-01-20",
                episodes=[
                    EpisodeMetadata(
                        season_number=1,
                        episode_number=1,
                        title="Pilot",
                        synopsis="Walter White begins.",
                        air_date="2008-01-20",
                        duration_seconds=3480,
                    ),
                ],
            ),
        ],
    )


@pytest.mark.unit
class TestEnrichSeriesMetadata:
    """Tests for EnrichSeriesMetadataUseCase."""

    @pytest.mark.asyncio
    async def test_should_enrich_series_with_metadata(self) -> None:
        series = _make_series()
        repo = AsyncMock(spec=SeriesRepository)
        repo.find_by_id.return_value = series
        repo.save.side_effect = lambda s: s

        provider = AsyncMock(spec=MetadataProvider)
        provider.search_series.return_value = _make_metadata()

        use_case = EnrichSeriesMetadataUseCase(series_repository=repo, primary_provider=provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(series.id)))

        assert result.enriched is True
        assert result.provider == "tmdb"

        saved = repo.save.call_args[0][0]
        assert saved.tmdb_id == TmdbId(1396)
        assert saved.synopsis is not None

    @pytest.mark.asyncio
    async def test_should_enrich_episode_title(self) -> None:
        series = _make_series()
        repo = AsyncMock(spec=SeriesRepository)
        repo.find_by_id.return_value = series
        repo.save.side_effect = lambda s: s

        provider = AsyncMock(spec=MetadataProvider)
        provider.search_series.return_value = _make_metadata()

        use_case = EnrichSeriesMetadataUseCase(series_repository=repo, primary_provider=provider)
        await use_case.execute(EnrichMediaInput(media_id=str(series.id)))

        saved = repo.save.call_args[0][0]
        episode = saved.seasons[0].episodes[0]
        assert episode.title.value == "Pilot"

    @pytest.mark.asyncio
    async def test_should_skip_already_enriched(self) -> None:
        series = _make_series()
        series = series.with_updates(tmdb_id=TmdbId(1396))

        repo = AsyncMock(spec=SeriesRepository)
        repo.find_by_id.return_value = series

        provider = AsyncMock(spec=MetadataProvider)
        use_case = EnrichSeriesMetadataUseCase(series_repository=repo, primary_provider=provider)

        result = await use_case.execute(EnrichMediaInput(media_id=str(series.id)))

        assert result.enriched is False

    @pytest.mark.asyncio
    async def test_should_raise_when_series_not_found(self) -> None:
        repo = AsyncMock(spec=SeriesRepository)
        repo.find_by_id.return_value = None

        provider = AsyncMock(spec=MetadataProvider)
        use_case = EnrichSeriesMetadataUseCase(series_repository=repo, primary_provider=provider)

        from src.modules.media.domain.value_objects import SeriesId

        fake_id = str(SeriesId.generate())
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(EnrichMediaInput(media_id=fake_id))

    @pytest.mark.asyncio
    async def test_should_enrich_double_episode(self) -> None:
        """Double episode file should merge metadata from two TMDB episodes."""
        series = _make_series()
        assert series.id is not None
        # Replace episode with a double-title one
        double_ep = Episode(
            series_id=series.id,
            season_number=1,
            episode_number=1,
            title=Title("Downtown as Fruits - Eugene_s Bike"),
            duration=Duration(0),
            files=[
                MediaFile(
                    file_path=FilePath("/series/ha/s01e01.avi"),
                    file_size=300_000,
                    resolution=Resolution("720p"),
                    is_primary=True,
                ),
            ],
        )
        season = Season(series_id=series.id, season_number=1)
        season = season.with_episode(double_ep)
        series = series.with_updates(seasons=[season])

        metadata = MediaMetadata(
            title="Hey! Arnold",
            tmdb_id=537,
            seasons=[
                SeasonMetadata(
                    season_number=1,
                    episodes=[
                        EpisodeMetadata(
                            season_number=1,
                            episode_number=1,
                            title="Downtown as Fruits",
                            synopsis="Arnold goes downtown.",
                            duration_seconds=660,
                        ),
                        EpisodeMetadata(
                            season_number=1,
                            episode_number=2,
                            title="Eugene's Bike",
                            synopsis="Eugene gets a new bike.",
                            duration_seconds=660,
                        ),
                    ],
                ),
            ],
        )

        repo = AsyncMock(spec=SeriesRepository)
        repo.find_by_id.return_value = series
        repo.save.side_effect = lambda s: s

        provider = AsyncMock(spec=MetadataProvider)
        provider.search_series.return_value = metadata

        use_case = EnrichSeriesMetadataUseCase(series_repository=repo, primary_provider=provider)
        await use_case.execute(EnrichMediaInput(media_id=str(series.id)))

        saved = repo.save.call_args[0][0]
        ep = saved.seasons[0].episodes[0]
        assert ep.title.value == "Downtown as Fruits / Eugene's Bike"
        assert ep.duration.value == 1320  # 660 + 660
        assert "Arnold goes downtown." in (ep.synopsis or "")
        assert "Eugene gets a new bike." in (ep.synopsis or "")

    @pytest.mark.asyncio
    async def test_should_not_overwrite_existing_fields_for_double_episode(self) -> None:
        """Double-episode enrichment must not overwrite existing episode fields."""
        series = _make_series()
        assert series.id is not None
        double_ep = Episode(
            series_id=series.id,
            season_number=1,
            episode_number=1,
            title=Title("Downtown as Fruits / Eugene's Bike"),
            duration=Duration(1320),
            synopsis="Existing synopsis that must be preserved.",
            files=[
                MediaFile(
                    file_path=FilePath("/series/ha/s01e01.avi"),
                    file_size=300_000,
                    resolution=Resolution("720p"),
                    is_primary=True,
                ),
            ],
        )
        season = Season(series_id=series.id, season_number=1)
        season = season.with_episode(double_ep)
        series = series.with_updates(seasons=[season])

        metadata = MediaMetadata(
            title="Hey! Arnold",
            tmdb_id=537,
            seasons=[
                SeasonMetadata(
                    season_number=1,
                    episodes=[
                        EpisodeMetadata(
                            season_number=1,
                            episode_number=1,
                            title="Downtown as Fruits",
                            synopsis="New synopsis from TMDB.",
                            duration_seconds=660,
                        ),
                        EpisodeMetadata(
                            season_number=1,
                            episode_number=2,
                            title="Eugene's Bike",
                            synopsis="Another TMDB synopsis.",
                            duration_seconds=660,
                        ),
                    ],
                ),
            ],
        )

        repo = AsyncMock(spec=SeriesRepository)
        repo.find_by_id.return_value = series
        repo.save.side_effect = lambda s: s

        provider = AsyncMock(spec=MetadataProvider)
        provider.search_series.return_value = metadata

        use_case = EnrichSeriesMetadataUseCase(series_repository=repo, primary_provider=provider)
        await use_case.execute(EnrichMediaInput(media_id=str(series.id)))

        saved = repo.save.call_args[0][0]
        ep = saved.seasons[0].episodes[0]
        # Title already has " / " so should NOT be overwritten
        assert ep.title.value == "Downtown as Fruits / Eugene's Bike"
        # Existing synopsis preserved
        assert ep.synopsis == "Existing synopsis that must be preserved."
        # Existing duration preserved
        assert ep.duration.value == 1320


@pytest.mark.unit
class TestDetectMultiEpisode:
    """Tests for _detect_multi_episode helper."""

    def test_single_generic_title(self):
        assert _detect_multi_episode("Episode 1") == 1

    def test_single_real_title(self):
        assert _detect_multi_episode("The Pilot") == 1

    def test_double_episode(self):
        assert _detect_multi_episode("Downtown as Fruits - Eugene_s Bike") == 2

    def test_triple_episode(self):
        assert _detect_multi_episode("Part 1 - Part 2 - Part 3") == 3

    def test_no_separator(self):
        assert _detect_multi_episode("A Simple Title") == 1

    def test_empty_title(self):
        assert _detect_multi_episode("") == 1
