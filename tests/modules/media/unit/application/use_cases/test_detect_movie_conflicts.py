"""Tests for DetectMovieConflictsUseCase (ADR-015 Phases 1 + 3)."""

from unittest.mock import AsyncMock

import pytest

from src.modules.media.application.dtos.conflict_dtos import DetectMovieConflictsInput
from src.modules.media.application.ports.library_health_port import LibraryHealthPort
from src.modules.media.application.use_cases.detect_movie_conflicts import (
    DetectMovieConflictsUseCase,
)
from src.modules.media.domain.entities import MediaConflict
from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    ResolutionAction,
    ResolutionSource,
    SuggestedAction,
)
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.events import MediaConflictDetectedEvent
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    TmdbId,
    Year,
)
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId
from src.modules.settings.domain.value_objects import ScanDedupConfig
from src.shared_kernel.integration_events import MovieMergedEvent
from tests.modules.media.unit.conftest import make_media_uow_mock


def _build_movie(
    *,
    external_id: str,
    duration_seconds: int = 7200,
    file_paths: list[str] | None = None,
    title: str = "Example",
    year: int = 2020,
    tmdb_id: int | None = 27205,
) -> Movie:
    files = [
        MediaFile(
            file_path=FilePath(p),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
            is_primary=True,
        )
        for p in (file_paths or [])
    ]
    return Movie(
        id=MovieId(external_id),
        library_id="lib_test12345678",
        title=Title(title),
        year=Year(year),
        duration=Duration(duration_seconds),
        files=files,
        tmdb_id=None if tmdb_id is None else TmdbId(tmdb_id),
    )


class _FakeLibraryHealth(LibraryHealthPort):
    """Deterministic LibraryHealthPort for unit tests."""

    def __init__(
        self,
        *,
        accessible_files: set[str] | None = None,
        healthy_libraries: set[str] | None = None,
    ) -> None:
        self._accessible_files = accessible_files or set()
        self._healthy_libraries = healthy_libraries or set()

    async def is_file_accessible(self, file_path: str) -> bool:
        return file_path in self._accessible_files

    async def is_library_root_accessible(self, library_id: str) -> bool:
        return library_id in self._healthy_libraries


class TestDetectMovieConflictsUseCase:
    @pytest.mark.asyncio
    async def test_no_other_movies_creates_no_conflicts(self) -> None:
        mocks = make_media_uow_mock()
        self_movie = _build_movie(external_id="mov_abcdefghijkl")
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie]

        use_case = DetectMovieConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        assert result.conflicts_created == 0
        assert result.conflict_ids == []
        mocks.media_conflicts.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_collision_creates_conflict_and_publishes_event(self) -> None:
        mocks = make_media_uow_mock()
        self_movie = _build_movie(external_id="mov_abcdefghijkl", duration_seconds=7200)
        other = _build_movie(external_id="mov_mnopqrstuvwx", duration_seconds=7320)
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie, other]
        mocks.media_conflicts.find_blocking_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id

        event_bus = AsyncMock()
        use_case = DetectMovieConflictsUseCase(uow_factory=mocks.factory, event_bus=event_bus)

        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        assert result.conflicts_created == 1
        mocks.media_conflicts.save.assert_called_once()
        saved_conflict = mocks.media_conflicts.save.call_args[0][0]
        assert isinstance(saved_conflict, MediaConflict)
        assert saved_conflict.match_reason is MatchReason.TMDB_ID
        # delta 7320 - 7200 = 120s = 2.0 min
        assert saved_conflict.runtime_delta_minutes == pytest.approx(2.0)

        event_bus.publish.assert_awaited_once()
        published = event_bus.publish.await_args[0][0]
        assert isinstance(published, MediaConflictDetectedEvent)
        assert published.candidate_a_id.value == "mov_abcdefghijkl"
        assert published.candidate_b_id.value == "mov_mnopqrstuvwx"

    @pytest.mark.asyncio
    async def test_tunable_thresholds_from_settings_flag_different_edit(self) -> None:
        # delta 7320 - 7200 = 120s = 2.0 min — LIKELY_SAME under the
        # ADR-015 defaults, but DIFFERENT_EDIT under the strict bucket.
        mocks = make_media_uow_mock()
        self_movie = _build_movie(external_id="mov_abcdefghijkl", duration_seconds=7200)
        other = _build_movie(external_id="mov_mnopqrstuvwx", duration_seconds=7320)
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie, other]
        mocks.media_conflicts.find_blocking_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id

        runtime_settings = AsyncMock()
        runtime_settings.scan_dedup.return_value = ScanDedupConfig(
            runtime_delta_abs_minutes=1.0,
            runtime_delta_relative=0.005,
        )
        use_case = DetectMovieConflictsUseCase(
            uow_factory=mocks.factory,
            runtime_settings=runtime_settings,
        )

        await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        saved_conflict = mocks.media_conflicts.save.call_args[0][0]
        assert saved_conflict.suggested_action is SuggestedAction.DIFFERENT_EDIT_SUSPECTED
        runtime_settings.scan_dedup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_pending_pair_is_skipped(self) -> None:
        mocks = make_media_uow_mock()
        self_movie = _build_movie(external_id="mov_abcdefghijkl")
        other = _build_movie(external_id="mov_mnopqrstuvwx")
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie, other]

        existing = MediaConflict.detect(
            candidate_a_id="mov_mnopqrstuvwx",
            candidate_a_type="movie",
            candidate_a_runtime_minutes=120.0,
            candidate_b_id="mov_abcdefghijkl",
            candidate_b_type="movie",
            candidate_b_runtime_minutes=120.0,
            match_reason=MatchReason.TMDB_ID,
        )
        mocks.media_conflicts.find_blocking_pair.return_value = existing

        event_bus = AsyncMock()
        use_case = DetectMovieConflictsUseCase(uow_factory=mocks.factory, event_bus=event_bus)

        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        assert result.conflicts_created == 0
        mocks.media_conflicts.save.assert_not_called()
        event_bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_self_movie_vanishing_returns_empty_result(self) -> None:
        # Defensive: enrichment fired but the source movie was deleted
        # between commit and handler dispatch — the candidate list
        # contains only the *other* movie. Use case should not create
        # a conflict against a non-existent left-hand side.
        mocks = make_media_uow_mock()
        other = _build_movie(external_id="mov_mnopqrstuvwx")
        mocks.movies.find_all_by_tmdb_id.return_value = [other]

        use_case = DetectMovieConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        assert result.conflicts_created == 0
        mocks.media_conflicts.save.assert_not_called()


async def _stamp_conflict_id(conflict: MediaConflict) -> MediaConflict:
    """Stand-in for the persistence side of ``save`` — assigns an id."""
    return conflict.with_updates(
        id=MediaConflictId("cnf_stamped12345"),
    )


def _settings_with(*, fallback: bool = True) -> AsyncMock:
    rs = AsyncMock()
    rs.scan_dedup.return_value = ScanDedupConfig(title_year_fallback_enabled=fallback)
    return rs


class TestTitleYearFallback:
    """ADR-015 Phase 4c — (normalized_original_title, year) fallback."""

    @pytest.mark.asyncio
    async def test_matches_unenriched_duplicate_by_title_and_year(self) -> None:
        mocks = make_media_uow_mock()
        enriched = _build_movie(
            external_id="mov_aaaaaaaaaaaa",
            title="Princess Mononoke",
            year=1997,
            tmdb_id=27205,
            file_paths=["/movies/a.mkv"],
        )
        unenriched = _build_movie(
            external_id="mov_bbbbbbbbbbbb",
            title="PRINCESS MONONOKE",
            year=1997,
            tmdb_id=None,
            file_paths=["/movies/b.mkv"],
        )
        # No TMDB collision; the dup only surfaces via title+year.
        mocks.movies.find_all_by_tmdb_id.return_value = [enriched]
        mocks.movies.find_all_by_year.return_value = [enriched, unenriched]
        mocks.media_conflicts.find_blocking_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id

        use_case = DetectMovieConflictsUseCase(
            uow_factory=mocks.factory,
            runtime_settings=_settings_with(fallback=True),
        )
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_aaaaaaaaaaaa", tmdb_id=27205),
        )

        assert result.conflicts_created == 1
        saved = mocks.media_conflicts.save.call_args[0][0]
        assert saved.match_reason is MatchReason.TITLE_YEAR_FALLBACK
        mocks.movies.find_all_by_year.assert_awaited_once_with(1997)

    @pytest.mark.asyncio
    async def test_fallback_disabled_skips_year_lookup(self) -> None:
        mocks = make_media_uow_mock()
        enriched = _build_movie(external_id="mov_aaaaaaaaaaaa", tmdb_id=27205)
        mocks.movies.find_all_by_tmdb_id.return_value = [enriched]

        use_case = DetectMovieConflictsUseCase(
            uow_factory=mocks.factory,
            runtime_settings=_settings_with(fallback=False),
        )
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_aaaaaaaaaaaa", tmdb_id=27205),
        )

        assert result.conflicts_created == 0
        mocks.movies.find_all_by_year.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_runtime_settings_disables_fallback(self) -> None:
        mocks = make_media_uow_mock()
        enriched = _build_movie(external_id="mov_aaaaaaaaaaaa", tmdb_id=27205)
        mocks.movies.find_all_by_tmdb_id.return_value = [enriched]

        use_case = DetectMovieConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_aaaaaaaaaaaa", tmdb_id=27205),
        )

        assert result.conflicts_created == 0
        mocks.movies.find_all_by_year.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_match_queues_never_auto_merges_orphan(self) -> None:
        mocks = make_media_uow_mock()
        enriched = _build_movie(
            external_id="mov_aaaaaaaaaaaa",
            title="Princess Mononoke",
            year=1997,
            tmdb_id=27205,
            file_paths=["/movies/a.mkv"],
        )
        orphan = _build_movie(
            external_id="mov_bbbbbbbbbbbb",
            title="Princess Mononoke",
            year=1997,
            tmdb_id=None,
            file_paths=["/movies/missing.mkv"],
        )
        mocks.movies.find_all_by_tmdb_id.return_value = [enriched]
        mocks.movies.find_all_by_year.return_value = [enriched, orphan]
        mocks.media_conflicts.find_blocking_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id

        # Orphan would auto-merge under a TMDB match — but the weaker
        # title+year identity must always queue instead.
        library_health = _FakeLibraryHealth(
            accessible_files={"/movies/a.mkv"},
            healthy_libraries={"lib_test12345678"},
        )
        use_case = DetectMovieConflictsUseCase(
            uow_factory=mocks.factory,
            library_health=library_health,
            runtime_settings=_settings_with(fallback=True),
        )
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_aaaaaaaaaaaa", tmdb_id=27205),
        )

        assert result.conflicts_created == 1
        saved = mocks.media_conflicts.save.call_args[0][0]
        assert saved.match_reason is MatchReason.TITLE_YEAR_FALLBACK
        assert saved.is_resolved is False
        mocks.movies.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_sweep_path_none_tmdb_skips_tmdb_pass_runs_fallback(self) -> None:
        # ADR-015 Phase 6.5 — the sweep invokes the detector with
        # ``tmdb_id=None`` for movies that never matched TMDB. The
        # detector must skip ``find_all_by_tmdb_id`` entirely and still
        # run the title+year fallback pass.
        mocks = make_media_uow_mock()
        unenriched_self = _build_movie(
            external_id="mov_aaaaaaaaaaaa",
            title="Princess Mononoke",
            year=1997,
            tmdb_id=None,
            file_paths=["/movies/a.mkv"],
        )
        unenriched_dup = _build_movie(
            external_id="mov_bbbbbbbbbbbb",
            title="Princess Mononoke",
            year=1997,
            tmdb_id=None,
            file_paths=["/movies/b.mkv"],
        )
        mocks.movies.find_by_id.return_value = unenriched_self
        mocks.movies.find_all_by_year.return_value = [unenriched_self, unenriched_dup]
        mocks.media_conflicts.find_blocking_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id

        use_case = DetectMovieConflictsUseCase(
            uow_factory=mocks.factory,
            runtime_settings=_settings_with(fallback=True),
        )
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_aaaaaaaaaaaa", tmdb_id=None),
        )

        assert result.conflicts_created == 1
        mocks.movies.find_all_by_tmdb_id.assert_not_called()
        saved = mocks.media_conflicts.save.call_args[0][0]
        assert saved.match_reason is MatchReason.TITLE_YEAR_FALLBACK

    @pytest.mark.asyncio
    async def test_sweep_path_none_tmdb_returns_empty_when_self_vanished(self) -> None:
        # If the sweep's snapshot id no longer resolves (movie deleted
        # mid-pass), the detector returns 0 instead of crashing.
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = None

        use_case = DetectMovieConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_aaaaaaaaaaaa", tmdb_id=None),
        )

        assert result.conflicts_created == 0
        mocks.media_conflicts.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_skips_ids_already_handled_by_tmdb_pass(self) -> None:
        mocks = make_media_uow_mock()
        enriched = _build_movie(
            external_id="mov_aaaaaaaaaaaa",
            title="Princess Mononoke",
            year=1997,
            tmdb_id=27205,
            file_paths=["/movies/a.mkv"],
        )
        # Same TMDB id AND same title+year — must produce a single
        # conflict (TMDB pass), not a duplicate from the fallback.
        other = _build_movie(
            external_id="mov_bbbbbbbbbbbb",
            title="Princess Mononoke",
            year=1997,
            tmdb_id=27205,
            file_paths=["/movies/b.mkv"],
        )
        mocks.movies.find_all_by_tmdb_id.return_value = [enriched, other]
        mocks.movies.find_all_by_year.return_value = [enriched, other]
        mocks.media_conflicts.find_blocking_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id

        use_case = DetectMovieConflictsUseCase(
            uow_factory=mocks.factory,
            runtime_settings=_settings_with(fallback=True),
        )
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_aaaaaaaaaaaa", tmdb_id=27205),
        )

        assert result.conflicts_created == 1
        assert mocks.media_conflicts.save.call_count == 1
        saved = mocks.media_conflicts.save.call_args[0][0]
        assert saved.match_reason is MatchReason.TMDB_ID


class TestAutoMergeOrphans:
    """ADR-015 Phase 3 — silent absorption of orphan candidates."""

    @pytest.mark.asyncio
    async def test_orphan_other_triggers_auto_merge_and_skips_queue(self) -> None:
        # Self has a live file; other's file is missing (orphan) but
        # the library is mounted → auto-merge other into self.
        mocks = make_media_uow_mock()
        self_movie = _build_movie(
            external_id="mov_abcdefghijkl",
            file_paths=["/movies/self.mkv"],
        )
        orphan = _build_movie(
            external_id="mov_mnopqrstuvwx",
            file_paths=["/movies/missing.mkv"],
        )
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie, orphan]
        mocks.media_conflicts.find_blocking_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id
        mocks.movies.delete.return_value = True

        health = _FakeLibraryHealth(
            accessible_files={"/movies/self.mkv"},  # orphan's path NOT here
            healthy_libraries={"lib_test12345678"},
        )
        event_bus = AsyncMock()
        use_case = DetectMovieConflictsUseCase(
            uow_factory=mocks.factory,
            library_health=health,
            event_bus=event_bus,
        )

        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        assert result.conflicts_created == 1
        saved_conflict = mocks.media_conflicts.save.call_args[0][0]
        assert saved_conflict.is_resolved is True
        assert saved_conflict.resolution is ResolutionAction.MERGE_REPLACE
        assert saved_conflict.resolution_source is ResolutionSource.AUTO
        assert saved_conflict.winner_id == "mov_abcdefghijkl"

        mocks.movies.delete.assert_awaited_once()
        deleted_arg = mocks.movies.delete.await_args[0][0]
        assert str(deleted_arg) == "mov_mnopqrstuvwx"

        event_bus.publish.assert_awaited_once()
        published = event_bus.publish.await_args[0][0]
        assert isinstance(published, MovieMergedEvent)
        assert published.is_auto is True
        assert published.winner_id.value == "mov_abcdefghijkl"
        assert published.loser_id.value == "mov_mnopqrstuvwx"

    @pytest.mark.asyncio
    async def test_unhealthy_library_falls_back_to_pending_queue(self) -> None:
        # File missing but library inaccessible — could be transient
        # I/O (drive unmounted); safer to queue the conflict.
        mocks = make_media_uow_mock()
        self_movie = _build_movie(
            external_id="mov_abcdefghijkl",
            file_paths=["/movies/self.mkv"],
        )
        other = _build_movie(
            external_id="mov_mnopqrstuvwx",
            file_paths=["/movies/elsewhere.mkv"],
        )
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie, other]
        mocks.media_conflicts.find_blocking_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id

        health = _FakeLibraryHealth(
            accessible_files={"/movies/self.mkv"},
            healthy_libraries=set(),  # library NOT in healthy set
        )
        event_bus = AsyncMock()
        use_case = DetectMovieConflictsUseCase(
            uow_factory=mocks.factory,
            library_health=health,
            event_bus=event_bus,
        )

        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        assert result.conflicts_created == 1
        saved_conflict = mocks.media_conflicts.save.call_args[0][0]
        # Falls back to the pending-conflict path; nothing is resolved.
        assert saved_conflict.is_resolved is False
        assert saved_conflict.resolution_source is None
        mocks.movies.delete.assert_not_called()

        # Detection event still fires; no merge event.
        published_types = [
            type(call.args[0]).__name__ for call in event_bus.publish.await_args_list
        ]
        assert published_types == ["MediaConflictDetectedEvent"]

    @pytest.mark.asyncio
    async def test_accessible_other_file_falls_back_to_pending_queue(self) -> None:
        # Other's file IS accessible — not an orphan, so the operator
        # must decide (Director's Cut? remaster?).
        mocks = make_media_uow_mock()
        self_movie = _build_movie(
            external_id="mov_abcdefghijkl",
            file_paths=["/movies/self.mkv"],
        )
        other = _build_movie(
            external_id="mov_mnopqrstuvwx",
            file_paths=["/movies/other.mkv"],
        )
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie, other]
        mocks.media_conflicts.find_blocking_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id

        health = _FakeLibraryHealth(
            accessible_files={"/movies/self.mkv", "/movies/other.mkv"},
            healthy_libraries={"lib_test12345678"},
        )
        use_case = DetectMovieConflictsUseCase(
            uow_factory=mocks.factory,
            library_health=health,
        )

        await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        saved_conflict = mocks.media_conflicts.save.call_args[0][0]
        assert saved_conflict.is_resolved is False
        mocks.movies.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_library_health_not_wired_preserves_phase1_behavior(self) -> None:
        # When the port is None, the use case never tries to detect
        # orphans — every collision queues as a pending conflict.
        mocks = make_media_uow_mock()
        self_movie = _build_movie(
            external_id="mov_abcdefghijkl",
            file_paths=["/movies/self.mkv"],
        )
        other = _build_movie(
            external_id="mov_mnopqrstuvwx",
            file_paths=["/movies/missing.mkv"],
        )
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie, other]
        mocks.media_conflicts.find_blocking_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id

        use_case = DetectMovieConflictsUseCase(
            uow_factory=mocks.factory,
            library_health=None,
        )

        await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        saved_conflict = mocks.media_conflicts.save.call_args[0][0]
        assert saved_conflict.is_resolved is False
        mocks.movies.delete.assert_not_called()
