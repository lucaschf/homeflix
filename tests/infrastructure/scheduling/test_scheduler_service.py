"""Tests for LibraryScanScheduler.

These tests exercise the reconciliation logic and job execution path
without starting a real APScheduler — we swap the ``_scheduler``
attribute for a lightweight fake that records add/remove calls.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.scheduling.scheduler_service import (
    LibraryScanScheduler,
    _job_id_for,
)
from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.value_objects.library_id import LibraryId
from src.modules.library.domain.value_objects.library_type import LibraryType


class _FakeJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id


class _FakeScheduler:
    """Minimal stand-in for APScheduler that records operations."""

    def __init__(self) -> None:
        self.running = False
        self.jobs: dict[str, dict[str, object]] = {}

    def start(self) -> None:
        self.running = True

    def shutdown(self, wait: bool = True) -> None:
        _ = wait  # signature parity with APScheduler
        self.running = False

    def add_job(self, func: object, **kwargs: object) -> None:
        key = str(kwargs["id"])
        self.jobs[key] = {"func": func, **kwargs}

    def remove_job(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)

    def get_jobs(self) -> list[_FakeJob]:
        return [_FakeJob(jid) for jid in self.jobs]


def _make_library(name: str = "Test", schedule: str | None = "0 * * * *") -> Library:
    return Library.create(
        name=name,
        library_type=LibraryType.MOVIES,
        paths=["/media/test"],
        scan_schedule=schedule,
    )


def _session_factory(session: object) -> object:
    """Build a callable that yields ``session`` from an ``async with``."""

    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


@pytest.fixture
def scheduler() -> LibraryScanScheduler:
    instance = LibraryScanScheduler(
        session_factory=MagicMock(),
        event_bus=MagicMock(),
        reconcile_interval_minutes=5,
    )
    instance._scheduler = _FakeScheduler()
    return instance


class TestReconcile:
    @pytest.mark.asyncio
    async def test_adds_job_for_each_library_with_schedule(
        self, scheduler: LibraryScanScheduler
    ) -> None:
        lib_a = _make_library("A", "0 3 * * *")
        lib_b = _make_library("B", "30 4 * * *")
        lib_no_sched = _make_library("C", schedule=None)

        repo = AsyncMock()
        repo.find_all.return_value = [lib_a, lib_b, lib_no_sched]
        scheduler._session_factory = _session_factory(MagicMock())  # type: ignore[assignment]

        with patch(
            "src.infrastructure.scheduling.scheduler_service.SqlAlchemyLibraryRepository",
            return_value=repo,
        ):
            await scheduler._reconcile()

        fake: _FakeScheduler = scheduler._scheduler
        assert _job_id_for(str(lib_a.id)) in fake.jobs
        assert _job_id_for(str(lib_b.id)) in fake.jobs
        assert _job_id_for(str(lib_no_sched.id)) not in fake.jobs

    @pytest.mark.asyncio
    async def test_removes_job_when_library_loses_schedule(
        self, scheduler: LibraryScanScheduler
    ) -> None:
        lib = _make_library("A", "0 3 * * *")
        job_id = _job_id_for(str(lib.id))
        fake: _FakeScheduler = scheduler._scheduler
        fake.jobs[job_id] = {"cron": "0 3 * * *"}

        lib_cleared = lib.with_updates(scan_schedule=None)

        repo = AsyncMock()
        repo.find_all.return_value = [lib_cleared]
        scheduler._session_factory = _session_factory(MagicMock())  # type: ignore[assignment]

        with patch(
            "src.infrastructure.scheduling.scheduler_service.SqlAlchemyLibraryRepository",
            return_value=repo,
        ):
            await scheduler._reconcile()

        assert job_id not in fake.jobs

    @pytest.mark.asyncio
    async def test_replaces_job_when_cron_changes(self, scheduler: LibraryScanScheduler) -> None:
        lib = _make_library("A", "0 3 * * *")
        job_id = _job_id_for(str(lib.id))
        fake: _FakeScheduler = scheduler._scheduler
        fake.jobs[job_id] = {"existing": True}

        lib_updated = lib.with_updates(scan_schedule="30 5 * * *")

        repo = AsyncMock()
        repo.find_all.return_value = [lib_updated]
        scheduler._session_factory = _session_factory(MagicMock())  # type: ignore[assignment]

        with patch(
            "src.infrastructure.scheduling.scheduler_service.SqlAlchemyLibraryRepository",
            return_value=repo,
        ):
            await scheduler._reconcile()

        assert job_id in fake.jobs
        # The job got replaced — our fake's `existing` marker is gone.
        assert "existing" not in fake.jobs[job_id]

    @pytest.mark.asyncio
    async def test_skips_invalid_cron_without_crashing(
        self, scheduler: LibraryScanScheduler
    ) -> None:
        # Passes the entity-level regex but fails real cron parsing.
        lib = _make_library("A", "99 99 * * *")

        repo = AsyncMock()
        repo.find_all.return_value = [lib]
        scheduler._session_factory = _session_factory(MagicMock())  # type: ignore[assignment]

        with patch(
            "src.infrastructure.scheduling.scheduler_service.SqlAlchemyLibraryRepository",
            return_value=repo,
        ):
            await scheduler._reconcile()  # must not raise

        fake: _FakeScheduler = scheduler._scheduler
        assert _job_id_for(str(lib.id)) not in fake.jobs


class TestRunScan:
    @pytest.mark.asyncio
    async def test_updates_last_scan_at_on_success(self, scheduler: LibraryScanScheduler) -> None:
        lib = _make_library("A", "0 * * * *")
        lib_id = str(lib.id)

        library_repo = AsyncMock()
        library_repo.find_by_id.return_value = lib
        library_repo.save = AsyncMock()

        session = AsyncMock()
        scheduler._session_factory = _session_factory(session)  # type: ignore[assignment]

        fake_use_case = AsyncMock()
        fake_use_case.execute.return_value = MagicMock(
            movies_created=1,
            movies_updated=0,
            episodes_created=0,
            episodes_updated=0,
            errors=[],
        )

        with (
            patch(
                "src.infrastructure.scheduling.scheduler_service.SqlAlchemyLibraryRepository",
                return_value=library_repo,
            ),
            patch(
                "src.infrastructure.scheduling.scheduler_service.ScanMediaDirectoriesUseCase",
                return_value=fake_use_case,
            ),
        ):
            await scheduler._run_scan(lib_id)

        library_repo.save.assert_awaited_once()
        await_args = library_repo.save.await_args
        assert await_args is not None
        saved = await_args.args[0]
        assert saved.last_scan_at is not None
        assert saved.last_scan_at.tzinfo == UTC
        assert saved.last_scan_at <= datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_skips_when_library_deleted_mid_run(
        self, scheduler: LibraryScanScheduler
    ) -> None:
        library_repo = AsyncMock()
        library_repo.find_by_id.return_value = None
        library_repo.save = AsyncMock()

        session = AsyncMock()
        scheduler._session_factory = _session_factory(session)  # type: ignore[assignment]

        with patch(
            "src.infrastructure.scheduling.scheduler_service.SqlAlchemyLibraryRepository",
            return_value=library_repo,
        ):
            await scheduler._run_scan(str(LibraryId.generate()))

        library_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rolls_back_on_scan_failure(self, scheduler: LibraryScanScheduler) -> None:
        lib = _make_library("A", "0 * * * *")
        library_repo = AsyncMock()
        library_repo.find_by_id.return_value = lib
        library_repo.save = AsyncMock()

        session = AsyncMock()
        scheduler._session_factory = _session_factory(session)  # type: ignore[assignment]

        fake_use_case = AsyncMock()
        fake_use_case.execute.side_effect = RuntimeError("scan blew up")

        with (
            patch(
                "src.infrastructure.scheduling.scheduler_service.SqlAlchemyLibraryRepository",
                return_value=library_repo,
            ),
            patch(
                "src.infrastructure.scheduling.scheduler_service.ScanMediaDirectoriesUseCase",
                return_value=fake_use_case,
            ),
        ):
            await scheduler._run_scan(str(lib.id))

        session.rollback.assert_awaited_once()
        library_repo.save.assert_not_awaited()
