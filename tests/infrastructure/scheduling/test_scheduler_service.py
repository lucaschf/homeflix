"""Tests for LibraryScanScheduler.

These tests exercise the reconciliation logic and job execution path
without starting a real APScheduler — we swap the ``_scheduler``
attribute for a lightweight fake that records add/remove calls.

Unit-of-Work factories are stubbed with a small helper that yields
an ``AsyncMock`` UoW so the scheduler can read and persist
libraries without touching a real database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.scheduling.scheduler_service import (
    LibraryScanScheduler,
    _job_id_for,
)
from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.value_objects.library_id import LibraryId
from src.modules.library.domain.value_objects.library_type import LibraryType
from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunStatus,
    ScanRunTrigger,
)
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId


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


def _build_uow(library_repo: AsyncMock) -> AsyncMock:
    """Build an async-context-manager UoW whose ``libraries`` is ``library_repo``."""
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.libraries = library_repo
    return uow


@pytest.fixture
def library_repo() -> AsyncMock:
    return AsyncMock()


def _make_run(library_id: str | None = "lib_test12345678") -> ScanRun:
    """Build a stub ``ScanRun`` that already has an id assigned."""
    return ScanRun(
        id=ScanRunId.generate(),
        kind=ScanRunKind.SCAN,
        trigger=ScanRunTrigger.SCHEDULED,
        library_id=library_id,
        status=ScanRunStatus.RUNNING,
    )


@pytest.fixture
def scan_run_service() -> AsyncMock:
    """Service mock — ``open_scan`` returns a fresh run with an id."""
    service = AsyncMock()
    service.open_scan.return_value = _make_run()
    return service


@pytest.fixture
def scheduler(
    library_repo: AsyncMock,
    scan_run_service: AsyncMock,
) -> LibraryScanScheduler:
    uow = _build_uow(library_repo)
    library_uow_factory = MagicMock(return_value=uow)
    from src.modules.settings.domain.value_objects import SchedulerConfig

    runtime_settings = AsyncMock()
    runtime_settings.scheduler = AsyncMock(return_value=SchedulerConfig())
    instance = LibraryScanScheduler(
        library_uow_factory=library_uow_factory,
        scan_run_service=scan_run_service,
        runtime_settings=runtime_settings,
    )
    instance._scheduler = _FakeScheduler()
    return instance


class TestReconcile:
    @pytest.mark.asyncio
    async def test_adds_job_for_each_library_with_schedule(
        self, scheduler: LibraryScanScheduler, library_repo: AsyncMock
    ) -> None:
        lib_a = _make_library("A", "0 3 * * *")
        lib_b = _make_library("B", "30 4 * * *")
        lib_no_sched = _make_library("C", schedule=None)
        library_repo.find_all.return_value = [lib_a, lib_b, lib_no_sched]

        await scheduler._reconcile()

        fake: _FakeScheduler = scheduler._scheduler
        assert _job_id_for(str(lib_a.id)) in fake.jobs
        assert _job_id_for(str(lib_b.id)) in fake.jobs
        assert _job_id_for(str(lib_no_sched.id)) not in fake.jobs

    @pytest.mark.asyncio
    async def test_removes_job_when_library_loses_schedule(
        self, scheduler: LibraryScanScheduler, library_repo: AsyncMock
    ) -> None:
        lib = _make_library("A", "0 3 * * *")
        job_id = _job_id_for(str(lib.id))
        fake: _FakeScheduler = scheduler._scheduler
        fake.jobs[job_id] = {"cron": "0 3 * * *"}

        lib_cleared = lib.with_updates(scan_schedule=None)
        library_repo.find_all.return_value = [lib_cleared]

        await scheduler._reconcile()

        assert job_id not in fake.jobs

    @pytest.mark.asyncio
    async def test_replaces_job_when_cron_changes(
        self, scheduler: LibraryScanScheduler, library_repo: AsyncMock
    ) -> None:
        lib = _make_library("A", "0 3 * * *")
        job_id = _job_id_for(str(lib.id))
        fake: _FakeScheduler = scheduler._scheduler
        fake.jobs[job_id] = {"existing": True}

        lib_updated = lib.with_updates(scan_schedule="30 5 * * *")
        library_repo.find_all.return_value = [lib_updated]

        await scheduler._reconcile()

        assert job_id in fake.jobs
        # The job got replaced — our fake's `existing` marker is gone.
        assert "existing" not in fake.jobs[job_id]

    @pytest.mark.asyncio
    async def test_skips_invalid_cron_without_crashing(
        self, scheduler: LibraryScanScheduler, library_repo: AsyncMock
    ) -> None:
        # Passes the entity-level regex but fails real cron parsing.
        lib = _make_library("A", "99 99 * * *")
        library_repo.find_all.return_value = [lib]

        await scheduler._reconcile()  # must not raise

        fake: _FakeScheduler = scheduler._scheduler
        assert _job_id_for(str(lib.id)) not in fake.jobs


class TestRunScan:
    @pytest.mark.asyncio
    async def test_updates_last_scan_at_on_success(
        self,
        scheduler: LibraryScanScheduler,
        library_repo: AsyncMock,
        scan_run_service: AsyncMock,
    ) -> None:
        lib = _make_library("A", "0 * * * *")
        library_repo.find_by_id.return_value = lib
        library_repo.save = AsyncMock()
        scan_run_service.open_scan.return_value = _make_run(str(lib.id))

        await scheduler._run_scan(str(lib.id))

        library_repo.save.assert_awaited_once()
        saved = library_repo.save.await_args.args[0]
        assert saved.last_scan_at is not None
        assert saved.last_scan_at.tzinfo == UTC
        assert saved.last_scan_at <= datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_skips_when_library_deleted_mid_run(
        self,
        scheduler: LibraryScanScheduler,
        library_repo: AsyncMock,
        scan_run_service: AsyncMock,
    ) -> None:
        library_repo.find_by_id.return_value = None
        library_repo.save = AsyncMock()

        await scheduler._run_scan(str(LibraryId.generate()))

        # No scan_runs row opened, no library save.
        scan_run_service.open_scan.assert_not_awaited()
        scan_run_service.run_scan.assert_not_awaited()
        library_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delegates_to_scan_run_service_with_scheduled_trigger(
        self,
        scheduler: LibraryScanScheduler,
        library_repo: AsyncMock,
        scan_run_service: AsyncMock,
    ) -> None:
        """The scheduler routes through ``ScanRunService`` so each run
        becomes a ``scan_runs`` row tagged ``scheduled``."""
        lib = _make_library("A", "0 * * * *")
        library_repo.find_by_id.return_value = lib
        library_repo.save = AsyncMock()
        run = _make_run(str(lib.id))
        scan_run_service.open_scan.return_value = run

        await scheduler._run_scan(str(lib.id))

        scan_run_service.open_scan.assert_awaited_once()
        kwargs = scan_run_service.open_scan.await_args.kwargs
        assert kwargs["library_id"] == str(lib.id)
        assert kwargs["trigger"] == ScanRunTrigger.SCHEDULED

        scan_run_service.run_scan.assert_awaited_once()
        run_args = scan_run_service.run_scan.await_args.args
        assert run_args[0] == run.id
        assert run_args[1] is lib
