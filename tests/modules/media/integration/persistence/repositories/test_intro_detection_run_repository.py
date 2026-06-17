"""Integration tests for SqlAlchemyIntroDetectionRunRepository."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities.intro_detection_run import (
    EpisodeDetectionResult,
    IntroDetectionRun,
)
from src.modules.media.domain.value_objects import IntroDetectionState
from src.modules.media.infrastructure.persistence.repositories.intro_detection_run_repository import (
    SqlAlchemyIntroDetectionRunRepository,
)


def _run(
    *,
    season_id: str,
    series_id: str = "ser_test00000001",
    season_number: int = 1,
    outcome: IntroDetectionState = IntroDetectionState.COMPLETED,
    episode_results: list[EpisodeDetectionResult] | None = None,
) -> IntroDetectionRun:
    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    return IntroDetectionRun(
        series_id=series_id,
        series_title="Test Series",
        season_id=season_id,
        season_number=season_number,
        algorithm="frame_hash",
        outcome=outcome,
        ref_count=3,
        analyzed_count=3,
        detected_count=2,
        persisted_count=1,
        min_confidence=0.7,
        episode_results=episode_results or [],
        started_at=now,
        finished_at=now,
    )


@pytest.mark.integration
class TestSqlAlchemyIntroDetectionRunRepository:
    async def test_add_assigns_id_and_round_trips(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyIntroDetectionRunRepository(db_session)
        run = _run(
            season_id="ssn_test00000001",
            episode_results=[
                EpisodeDetectionResult(
                    episode_id="epi_aaaaaaaaaaaa",
                    episode_number=1,
                    start_seconds=0.0,
                    end_seconds=60.0,
                    confidence=0.9,
                    persisted=True,
                ),
                EpisodeDetectionResult(
                    episode_id="epi_bbbbbbbbbbbb",
                    episode_number=2,
                    start_seconds=0.0,
                    end_seconds=55.0,
                    confidence=0.62,
                    persisted=False,
                ),
            ],
        )

        saved = await repo.add(run)

        assert saved.id is not None
        assert str(saved.id).startswith("idr_")
        found = await repo.find_by_id(saved.id)
        assert found is not None
        assert found.series_title == "Test Series"
        assert found.outcome is IntroDetectionState.COMPLETED
        assert found.detected_count == 2
        assert found.persisted_count == 1
        assert len(found.episode_results) == 2
        dropped = next(r for r in found.episode_results if not r.persisted)
        assert dropped.confidence == pytest.approx(0.62)
        assert dropped.episode_number == 2

    async def test_list_paginated_newest_first_and_filter_by_season(
        self, db_session: AsyncSession
    ) -> None:
        repo = SqlAlchemyIntroDetectionRunRepository(db_session)
        await repo.add(_run(season_id="ssn_aaaa00000001"))
        await repo.add(_run(season_id="ssn_bbbb00000002"))
        await repo.add(_run(season_id="ssn_aaaa00000001"))

        all_runs = await repo.list_paginated()
        assert len(all_runs) == 3

        only_a = await repo.list_paginated(season_id="ssn_aaaa00000001")
        assert len(only_a) == 2
        assert all(r.season_id == "ssn_aaaa00000001" for r in only_a)

        assert await repo.count() == 3
        assert await repo.count(season_id="ssn_aaaa00000001") == 2
