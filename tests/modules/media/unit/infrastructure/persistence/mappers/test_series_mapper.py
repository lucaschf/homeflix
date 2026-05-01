"""Unit tests for SeriesMapper, SeasonMapper, and EpisodeMapper."""

from datetime import UTC, datetime

import pytest

from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.value_objects import (
    CastMember,
    Duration,
    EpisodeId,
    FilePath,
    IntroDetectionState,
    IntroMarker,
    IntroMarkerSource,
    MediaFile,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.mappers import (
    EpisodeMapper,
    SeasonMapper,
    SeriesMapper,
)
from src.modules.media.infrastructure.persistence.models import (
    EpisodeModel,
    SeasonModel,
    SeriesModel,
)


def _create_episode(
    episode_id: EpisodeId | None = None,
    series_id: SeriesId | None = None,
) -> Episode:
    """Create an Episode entity for testing."""
    return Episode(
        id=episode_id,
        series_id=series_id or SeriesId.generate(),
        season_number=1,
        episode_number=1,
        title=Title("Test Episode"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath("/series/s01e01.mkv"),
                file_size=500_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


def _create_season(
    season_id: SeasonId | None = None,
    series_id: SeriesId | None = None,
) -> Season:
    """Create a Season entity for testing."""
    return Season(
        id=season_id,
        series_id=series_id or SeriesId.generate(),
        season_number=1,
        title=Title("Season 1"),
    )


def _create_series(series_id: SeriesId | None = None) -> Series:
    """Create a Series entity for testing."""
    return Series(
        id=series_id,
        title=Title("Test Series"),
        start_year=Year(2020),
    )


@pytest.mark.unit
class TestEpisodeMapper:
    """Unit tests for EpisodeMapper."""

    def test_to_model_raises_when_id_is_none(self) -> None:
        """Test that to_model raises ValueError when entity has no ID."""
        episode = _create_episode(episode_id=None)

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            EpisodeMapper.to_model(episode, season_id=1)

    def test_to_model_converts_entity_correctly(self) -> None:
        """Test that to_model converts all fields correctly."""
        episode_id = EpisodeId.generate()
        series_id = SeriesId.generate()
        episode = _create_episode(episode_id=episode_id, series_id=series_id)

        model = EpisodeMapper.to_model(episode, season_id=42)

        assert model.external_id == str(episode_id)
        assert model.season_id == 42
        assert model.series_external_id == str(series_id)
        assert model.title == "Test Episode"

    def test_to_model_leaves_intro_columns_null_when_intro_absent(self) -> None:
        episode = _create_episode(episode_id=EpisodeId.generate())

        model = EpisodeMapper.to_model(episode, season_id=1)

        assert model.intro_start_seconds is None
        assert model.intro_end_seconds is None
        assert model.intro_source is None
        assert model.intro_confidence is None
        assert model.intro_detected_at is None

    def test_to_model_explodes_auto_detected_intro(self) -> None:
        marker = IntroMarker(
            start_seconds=12,
            end_seconds=98,
            source=IntroMarkerSource.AUTO_DETECTED,
            confidence=0.92,
        )
        episode = _create_episode(episode_id=EpisodeId.generate()).with_intro_marker(marker)

        model = EpisodeMapper.to_model(episode, season_id=1)

        assert model.intro_start_seconds == 12
        assert model.intro_end_seconds == 98
        assert model.intro_source == "AUTO_DETECTED"
        assert model.intro_confidence == pytest.approx(0.92)

    def test_to_entity_reconstructs_manual_intro(self) -> None:
        episode_id = EpisodeId.generate()
        series_id = SeriesId.generate()
        now = datetime.now(UTC)
        model = EpisodeModel(
            external_id=str(episode_id),
            season_id=1,
            series_external_id=str(series_id),
            season_number=1,
            episode_number=1,
            title="Pilot",
            duration=2700,
            file_path="/series/s01e01.mkv",
            file_size=1_000_000,
            resolution="1080p",
            intro_start_seconds=0,
            intro_end_seconds=60,
            intro_source="MANUAL",
            intro_confidence=None,
            intro_detected_at=now,
            created_at=now,
            updated_at=now,
        )

        entity = EpisodeMapper.to_entity(model)

        assert entity.intro is not None
        assert entity.intro.source == IntroMarkerSource.MANUAL
        assert entity.intro.confidence is None
        assert entity.intro.start_seconds == 0
        assert entity.intro.end_seconds == 60

    def test_to_entity_returns_none_intro_when_columns_null(self) -> None:
        episode_id = EpisodeId.generate()
        series_id = SeriesId.generate()
        now = datetime.now(UTC)
        model = EpisodeModel(
            external_id=str(episode_id),
            season_id=1,
            series_external_id=str(series_id),
            season_number=1,
            episode_number=1,
            title="Pilot",
            duration=2700,
            file_path="/series/s01e01.mkv",
            file_size=1_000_000,
            resolution="1080p",
            created_at=now,
            updated_at=now,
        )

        entity = EpisodeMapper.to_entity(model)

        assert entity.intro is None


@pytest.mark.unit
class TestSeasonMapper:
    """Unit tests for SeasonMapper."""

    def test_to_model_raises_when_id_is_none(self) -> None:
        """Test that to_model raises ValueError when entity has no ID."""
        season = _create_season(season_id=None)

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            SeasonMapper.to_model(season, series_db_id=1)

    def test_to_model_converts_entity_correctly(self) -> None:
        """Test that to_model converts all fields correctly."""
        season_id = SeasonId.generate()
        series_id = SeriesId.generate()
        season = _create_season(season_id=season_id, series_id=series_id)

        model = SeasonMapper.to_model(season, series_db_id=42)

        assert model.external_id == str(season_id)
        assert model.series_id == 42
        assert model.series_external_id == str(series_id)

    def test_to_model_serializes_detection_state(self) -> None:
        season = _create_season(season_id=SeasonId.generate())
        attempted_at = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
        season = season.with_updates(
            intro_detection_state=IntroDetectionState.FAILED,
            intro_detection_attempted_at=attempted_at,
            intro_detection_error="boom",
        )

        model = SeasonMapper.to_model(season, series_db_id=1)

        assert model.intro_detection_state == "FAILED"
        assert model.intro_detection_attempted_at == attempted_at
        assert model.intro_detection_error == "boom"

    def test_to_entity_reconstructs_detection_state(self) -> None:
        season_id = SeasonId.generate()
        series_id = SeriesId.generate()
        now = datetime.now(UTC)
        model = SeasonModel(
            external_id=str(season_id),
            series_id=1,
            series_external_id=str(series_id),
            season_number=1,
            title="Season 1",
            intro_detection_state="COMPLETED",
            intro_detection_attempted_at=now,
            intro_detection_error=None,
            created_at=now,
            updated_at=now,
        )

        entity = SeasonMapper.to_entity(model)

        assert entity.intro_detection_state == IntroDetectionState.COMPLETED
        assert entity.intro_detection_attempted_at == now
        assert entity.intro_detection_error is None


@pytest.mark.unit
class TestSeriesMapper:
    """Unit tests for SeriesMapper."""

    def test_to_model_raises_when_id_is_none(self) -> None:
        """Test that to_model raises ValueError when entity has no ID."""
        series = _create_series(series_id=None)

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            SeriesMapper.to_model(series)

    def test_to_model_converts_entity_correctly(self) -> None:
        """Test that to_model converts all fields correctly."""
        series_id = SeriesId.generate()
        series = _create_series(series_id=series_id)

        model = SeriesMapper.to_model(series)

        assert model.external_id == str(series_id)
        assert model.title == "Test Series"
        assert model.start_year == 2020

    def test_to_entity_shallow_returns_empty_seasons(self) -> None:
        """``include_seasons=False`` skips the seasons relationship.

        The search path uses this so it never triggers a lazy-load
        of seasons / episodes / file_variants on the way to building
        a ``SearchItemOutput`` (which only reads root fields and the
        ``localized`` JSON). Pinning this contract keeps a future
        refactor from silently re-enabling the heavy fan-out.
        """
        series_id = SeriesId.generate()
        now = datetime.now(UTC)
        model = SeriesModel(
            external_id=str(series_id),
            title="Shallow Series",
            start_year=2020,
            created_at=now,
            updated_at=now,
        )

        entity = SeriesMapper.to_entity(model, include_seasons=False)

        assert entity.id == series_id
        assert entity.title.value == "Shallow Series"
        assert entity.start_year.value == 2020
        assert entity.seasons == []

    def test_cast_roundtrips_through_to_model_and_to_entity(self) -> None:
        """A series carrying a populated cast list survives one
        ``to_model`` → ``to_entity`` cycle byte-for-byte. Pins that
        the JSON encoding stays the same shape that the movie-side
        decoder already understands so shared helpers don't drift."""
        series = _create_series(series_id=SeriesId.generate()).with_updates(
            cast=[
                CastMember(
                    name="Bryan Cranston",
                    profile_path="https://image.tmdb.org/t/p/original/bryan.jpg",
                    role="Walter White",
                    tmdb_id=17419,
                ),
                CastMember(name="Aaron Paul", role="Jesse Pinkman"),
            ],
        )

        model = SeriesMapper.to_model(series)
        # Stamp creation timestamps so to_entity can rebuild without
        # the DB defaults that aren't applied in unit tests.
        now = datetime.now(UTC)
        model.created_at = now
        model.updated_at = now

        rebuilt = SeriesMapper.to_entity(model, include_seasons=False)

        assert len(rebuilt.cast) == 2
        assert rebuilt.cast[0].name == "Bryan Cranston"
        assert rebuilt.cast[0].profile_path == "https://image.tmdb.org/t/p/original/bryan.jpg"
        assert rebuilt.cast[0].role == "Walter White"
        assert rebuilt.cast[0].tmdb_id == 17419
        assert rebuilt.cast[1].name == "Aaron Paul"
        assert rebuilt.cast[1].profile_path is None
        assert rebuilt.cast[1].tmdb_id is None

    def test_update_model_overwrites_existing_cast(self) -> None:
        """``update_model`` replaces the persisted cast wholesale
        rather than merging — the new entity's list is the source of
        truth, matching how MovieMapper handles re-enrichment."""
        series_id = SeriesId.generate()
        existing = SeriesMapper.to_model(
            _create_series(series_id=series_id).with_updates(
                cast=[CastMember(name="Old Actor")],
            ),
        )

        refreshed = _create_series(series_id=series_id).with_updates(
            cast=[CastMember(name="New Actor", tmdb_id=42)],
        )

        SeriesMapper.update_model(existing, refreshed)
        assert "New Actor" in (existing.cast or "")
        assert "Old Actor" not in (existing.cast or "")
