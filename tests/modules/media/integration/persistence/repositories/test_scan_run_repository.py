"""Integration tests for SqlAlchemyScanRunRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunStatus,
    ScanRunTrigger,
)
from src.modules.media.infrastructure.persistence.repositories.scan_run_repository import (
    SqlAlchemyScanRunRepository,
)


def _new_scan(library_id: str | None = "lib_test12345678") -> ScanRun:
    return ScanRun.start(
        kind=ScanRunKind.SCAN,
        trigger=ScanRunTrigger.MANUAL,
        library_id=library_id,
    )


@pytest.mark.integration
class TestSaveAndFind:
    async def test_save_should_assign_external_id_on_first_persist(
        self, db_session: AsyncSession
    ) -> None:
        repo = SqlAlchemyScanRunRepository(db_session)
        saved = await repo.save(_new_scan())

        assert saved.id is not None
        assert str(saved.id).startswith("run_")
        assert saved.status == ScanRunStatus.RUNNING

    async def test_save_should_update_in_place_on_terminal_transition(
        self, db_session: AsyncSession
    ) -> None:
        repo = SqlAlchemyScanRunRepository(db_session)
        opened = await repo.save(_new_scan())

        finalized = opened.succeed({"movies_created": 5}, ["err1"])
        await repo.save(finalized)
        again = await repo.find_by_id(opened.id)  # type: ignore[arg-type]

        assert again is not None
        assert again.status == ScanRunStatus.SUCCEEDED
        assert again.summary == {"movies_created": 5}
        assert again.errors == ["err1"]
        assert again.finished_at is not None


@pytest.mark.integration
class TestListAndCount:
    async def test_list_paginated_should_filter_by_kind(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyScanRunRepository(db_session)
        await repo.save(_new_scan())
        await repo.save(
            ScanRun.start(
                kind=ScanRunKind.ENRICH,
                trigger=ScanRunTrigger.MANUAL,
                library_id=None,
            ),
        )

        scans = await repo.list_paginated(kind=ScanRunKind.SCAN)
        enriches = await repo.list_paginated(kind=ScanRunKind.ENRICH)

        assert len(scans) == 1
        assert len(enriches) == 1
        assert scans[0].kind == ScanRunKind.SCAN
        assert enriches[0].kind == ScanRunKind.ENRICH

    async def test_list_paginated_should_filter_by_trigger(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyScanRunRepository(db_session)
        await repo.save(_new_scan())
        await repo.save(
            ScanRun.start(
                kind=ScanRunKind.SCAN,
                trigger=ScanRunTrigger.SCHEDULED,
                library_id="lib_test12345678",
            ),
        )

        manual = await repo.list_paginated(trigger=ScanRunTrigger.MANUAL)
        scheduled = await repo.list_paginated(trigger=ScanRunTrigger.SCHEDULED)

        assert len(manual) == 1
        assert len(scheduled) == 1

    async def test_count_should_respect_filters(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyScanRunRepository(db_session)
        for _ in range(3):
            await repo.save(_new_scan())

        assert await repo.count(kind=ScanRunKind.SCAN) == 3
        assert await repo.count(kind=ScanRunKind.ENRICH) == 0


@pytest.mark.integration
class TestListByStatus:
    async def test_should_return_only_matching_status(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyScanRunRepository(db_session)
        opened = await repo.save(_new_scan())
        await repo.save(opened.succeed({}, []))
        await repo.save(_new_scan())  # second row stays running

        running = await repo.list_by_status(ScanRunStatus.RUNNING)
        succeeded = await repo.list_by_status(ScanRunStatus.SUCCEEDED)

        assert len(running) == 1
        assert len(succeeded) == 1
