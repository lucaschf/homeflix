"""Contract tests for the abstract UnitOfWork base."""

from types import TracebackType
from typing import Self

import pytest

from src.building_blocks.application.unit_of_work import UnitOfWork


class _RecordingUnitOfWork(UnitOfWork):
    """Minimal concrete implementation used to verify the contract.

    Tracks the lifecycle calls so tests can assert enter/exit/commit/
    rollback ordering without touching a real database.
    """

    def __init__(self) -> None:
        self.events: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> Self:
        self.events.append("enter")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is None:
            await self.commit()
        else:
            await self.rollback()
        self.events.append("exit")

    async def commit(self) -> None:
        self.commits += 1
        self.events.append("commit")

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.events.append("rollback")


@pytest.mark.unit
class TestUnitOfWorkContract:
    """Every UoW must commit on success and rollback on failure."""

    @pytest.mark.asyncio
    async def test_should_commit_on_clean_exit(self) -> None:
        uow = _RecordingUnitOfWork()

        async with uow:
            pass

        assert uow.events == ["enter", "commit", "exit"]
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_should_rollback_on_exception_and_propagate(self) -> None:
        uow = _RecordingUnitOfWork()

        with pytest.raises(RuntimeError, match="boom"):
            async with uow:
                raise RuntimeError("boom")

        assert uow.events == ["enter", "rollback", "exit"]
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_should_allow_explicit_commit_inside_context(self) -> None:
        uow = _RecordingUnitOfWork()

        async with uow:
            await uow.commit()

        assert uow.commits == 2  # explicit + auto on exit

    def test_should_refuse_instantiation_without_implementing_abstract_methods(self) -> None:
        with pytest.raises(TypeError):
            UnitOfWork()  # type: ignore[abstract]
