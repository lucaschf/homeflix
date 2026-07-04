"""Integration tests for SqlAlchemySubtitleOcrRunRepository."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities.subtitle_ocr_run import (
    SubtitleOcrRun,
    SubtitleTrackOcrResult,
)
from src.modules.media.domain.value_objects.subtitle_ocr_outcome import (
    SubtitleOcrOutcome,
    SubtitleTrackOutcome,
)
from src.modules.media.infrastructure.persistence.repositories.subtitle_ocr_run_repository import (
    SqlAlchemySubtitleOcrRunRepository,
)


def _run(
    *,
    media_id: str,
    media_kind: str = "movie",
    outcome: SubtitleOcrOutcome = SubtitleOcrOutcome.COMPLETED,
    track_results: list[SubtitleTrackOcrResult] | None = None,
) -> SubtitleOcrRun:
    now = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    return SubtitleOcrRun(
        media_kind=media_kind,
        media_id=media_id,
        media_title="Nausicaa",
        file_path="G:/movies/nausicaa.mkv",
        outcome=outcome,
        image_track_count=len(track_results or []),
        extracted_count=sum(
            1 for r in (track_results or []) if r.outcome == SubtitleTrackOutcome.EXTRACTED
        ),
        track_results=track_results or [],
        started_at=now,
        finished_at=now,
    )


@pytest.mark.integration
class TestSqlAlchemySubtitleOcrRunRepository:
    async def test_add_assigns_id_and_round_trips(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemySubtitleOcrRunRepository(db_session)
        run = _run(
            media_id="mov_aaaaaaaaaaaa",
            track_results=[
                SubtitleTrackOcrResult(
                    track_index=0,
                    language="en",
                    outcome=SubtitleTrackOutcome.EXTRACTED,
                    cue_count=1079,
                ),
                SubtitleTrackOcrResult(
                    track_index=2,
                    language="fr",
                    outcome=SubtitleTrackOutcome.SKIPPED_LANGUAGE,
                ),
            ],
        )

        saved = await repo.add(run)

        assert saved.id is not None
        assert str(saved.id).startswith("sor_")
        found = await repo.find_by_id(saved.id)
        assert found is not None
        assert found.media_kind == "movie"
        assert found.media_title == "Nausicaa"
        assert found.outcome is SubtitleOcrOutcome.COMPLETED
        assert found.image_track_count == 2
        assert found.extracted_count == 1
        assert len(found.track_results) == 2
        extracted = next(
            r for r in found.track_results if r.outcome == SubtitleTrackOutcome.EXTRACTED
        )
        assert extracted.language == "en"
        assert extracted.cue_count == 1079

    async def test_list_paginated_newest_first_and_filter(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemySubtitleOcrRunRepository(db_session)
        await repo.add(_run(media_id="mov_a", media_kind="movie"))
        await repo.add(_run(media_id="epi_b", media_kind="episode"))
        await repo.add(_run(media_id="mov_a", media_kind="movie"))

        assert len(await repo.list_paginated()) == 3

        only_movies = await repo.list_paginated(media_kind="movie")
        assert len(only_movies) == 2
        assert all(r.media_kind == "movie" for r in only_movies)

        only_a = await repo.list_paginated(media_id="mov_a")
        assert len(only_a) == 2

        assert await repo.count() == 3
        assert await repo.count(media_kind="episode") == 1
