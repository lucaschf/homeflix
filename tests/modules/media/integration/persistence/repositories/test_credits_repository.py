"""Integration tests for the per-file credits repository methods.

Covers ``find_*_pending_credits_detection`` + ``update_*_credits`` on a
real SQLite session for both movies (movie repo) and episodes (series
repo) — the round trip the credits job relies on.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.value_objects import (
    CreditsDetectionState,
    CreditsMarker,
    CreditsMarkerSource,
    Duration,
    EpisodeId,
    EpisodeNumber,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    SeasonId,
    SeasonNumber,
    SeriesId,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)

_LIBRARY_ID = "lib_credits12345"


def _movie() -> Movie:
    return Movie(
        id=MovieId.generate(),
        library_id=_LIBRARY_ID,
        title=Title("Credit Movie"),
        year=Year(2021),
        duration=Duration(6000),
        files=[
            MediaFile(
                file_path=FilePath("/movies/credit.mkv"),
                file_size=1,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


def _series_with_episode() -> Series:
    sid = SeriesId.generate()
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=sid,
        season_number=SeasonNumber(1),
        episode_number=EpisodeNumber(1),
        title=Title("Credit Episode"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath("/series/s01e01.mkv"),
                file_size=1,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    season = Season(
        id=SeasonId.generate(),
        series_id=sid,
        season_number=SeasonNumber(1),
        title=Title("Season 1"),
        episodes=[episode],
    )
    return Series(
        id=sid,
        library_id=_LIBRARY_ID,
        title=Title("Credit Series"),
        start_year=Year(2021),
        seasons=[season],
    )


@pytest.mark.integration
class TestMovieCreditsRepository:
    async def test_pending_then_update_round_trip(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie()
        await repo.save(movie)
        movie_id = movie.id
        assert movie_id is not None

        pending = await repo.find_pending_credits_detection(10)
        assert movie_id in {m.id for m in pending}

        marker = CreditsMarker(
            start_seconds=5400, source=CreditsMarkerSource.AUTO_DETECTED, confidence=0.8
        )
        updated = await repo.update_movie_credits(movie_id, marker, CreditsDetectionState.COMPLETED)
        assert updated is True

        # No longer pending; marker round-trips.
        pending_after = await repo.find_pending_credits_detection(10)
        assert movie_id not in {m.id for m in pending_after}
        reloaded = await repo.find_by_id(movie_id)
        assert reloaded is not None
        assert reloaded.credits is not None
        assert reloaded.credits.start_seconds == 5400
        assert reloaded.credits_detection_state is CreditsDetectionState.COMPLETED

    async def test_status_counts_and_listing(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie()
        await repo.save(movie)
        assert movie.id is not None
        await repo.update_movie_credits(
            movie.id,
            CreditsMarker(
                start_seconds=5400, source=CreditsMarkerSource.AUTO_DETECTED, confidence=0.8
            ),
            CreditsDetectionState.COMPLETED,
        )

        counts = await repo.count_credits_states()
        assert counts.get(CreditsDetectionState.COMPLETED.value, 0) >= 1

        rows, total = await repo.list_credits_status(
            CreditsDetectionState.COMPLETED.value, limit=50, offset=0
        )
        assert total >= 1
        row = next(r for r in rows if r.media_id == str(movie.id))
        assert row.start_seconds == 5400
        assert row.source == CreditsMarkerSource.AUTO_DETECTED.value
        assert row.series_id is None  # movies carry no episode context


@pytest.mark.integration
class TestEpisodeCreditsRepository:
    async def test_pending_then_update_round_trip(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _series_with_episode()
        await repo.save(series)
        episode_id = series.seasons[0].episodes[0].id
        assert episode_id is not None

        pending = await repo.find_episodes_pending_credits_detection(10)
        assert episode_id in {e.id for e in pending}

        marker = CreditsMarker(start_seconds=2500, source=CreditsMarkerSource.MANUAL)
        updated = await repo.update_episode_credits(
            episode_id, marker, CreditsDetectionState.COMPLETED
        )
        assert updated is True

        pending_after = await repo.find_episodes_pending_credits_detection(10)
        assert episode_id not in {e.id for e in pending_after}
        reloaded = await repo.find_episode_by_id(episode_id)
        assert reloaded is not None
        assert reloaded.credits is not None
        assert reloaded.credits.start_seconds == 2500
        assert reloaded.credits.is_manual

    async def test_status_listing_carries_episode_context(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _series_with_episode()
        await repo.save(series)
        episode_id = series.seasons[0].episodes[0].id
        assert episode_id is not None
        await repo.update_episode_credits(
            episode_id,
            CreditsMarker(start_seconds=2500, source=CreditsMarkerSource.MANUAL),
            CreditsDetectionState.COMPLETED,
        )

        counts = await repo.count_episode_credits_states()
        assert counts.get(CreditsDetectionState.COMPLETED.value, 0) >= 1

        rows, total = await repo.list_episode_credits_status(
            CreditsDetectionState.COMPLETED.value, limit=50, offset=0
        )
        assert total >= 1
        row = next(r for r in rows if r.media_id == str(episode_id))
        assert row.series_id == str(series.id)
        assert row.season_number == 1
        assert row.episode_number == 1
