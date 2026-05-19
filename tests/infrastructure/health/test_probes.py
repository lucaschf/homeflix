"""Unit tests for the readiness probes."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.health.probes import (
    DatabaseProbe,
    FilesystemProbe,
    ProbeStatus,
)


def _session_factory_from(execute_side_effect: Any | None = None) -> MagicMock:
    """Build an async-context session factory whose ``execute`` is configurable."""
    session = AsyncMock()
    if execute_side_effect is not None:
        session.execute.side_effect = execute_side_effect
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    return MagicMock(return_value=session)


def _library_uow_factory(libraries: list[Any]) -> MagicMock:
    """Async-context UoW whose ``libraries.find_all`` returns ``libraries``."""
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.libraries = AsyncMock()
    uow.libraries.find_all.return_value = libraries
    return MagicMock(return_value=uow)


def _library_stub(name: str, paths: list[str]) -> MagicMock:
    stub = MagicMock()
    stub.name = name
    stub.paths = [MagicMock(value=p) for p in paths]
    return stub


pytestmark = pytest.mark.unit


class TestDatabaseProbe:
    async def test_should_be_healthy_when_select_succeeds(self) -> None:
        probe = DatabaseProbe(session_factory=_session_factory_from())

        result = await probe.execute()

        assert result.status == ProbeStatus.HEALTHY
        assert result.message is None
        assert result.name == "database"

    async def test_should_be_unhealthy_when_session_raises(self) -> None:
        probe = DatabaseProbe(
            session_factory=_session_factory_from(RuntimeError("connection lost")),
        )

        result = await probe.execute()

        assert result.status == ProbeStatus.UNHEALTHY
        assert result.message is not None
        assert "connection lost" in result.message


class TestFilesystemProbe:
    async def test_should_be_healthy_when_every_path_exists(
        self,
        tmp_path,
    ) -> None:
        existing = tmp_path / "movies"
        existing.mkdir()
        probe = FilesystemProbe(
            library_uow_factory=_library_uow_factory(
                [_library_stub("A", [str(existing)])],
            ),
        )

        result = await probe.execute()

        assert result.status == ProbeStatus.HEALTHY
        assert result.message is None

    async def test_should_be_healthy_when_no_libraries_configured(self) -> None:
        # Fresh install with zero libraries — we don't want the
        # admin Health page to scream red before setup completes.
        probe = FilesystemProbe(library_uow_factory=_library_uow_factory([]))

        result = await probe.execute()

        assert result.status == ProbeStatus.HEALTHY

    async def test_should_be_degraded_when_one_library_has_missing_path(
        self,
        tmp_path,
    ) -> None:
        ok = tmp_path / "ok"
        ok.mkdir()
        probe = FilesystemProbe(
            library_uow_factory=_library_uow_factory(
                [
                    _library_stub("A", [str(ok)]),
                    _library_stub("B", [str(tmp_path / "missing")]),
                ],
            ),
        )

        result = await probe.execute()

        assert result.status == ProbeStatus.DEGRADED
        assert result.message is not None
        assert "B" in result.message
        assert "missing" in result.message

    async def test_should_be_unhealthy_when_every_library_is_broken(
        self,
        tmp_path,
    ) -> None:
        probe = FilesystemProbe(
            library_uow_factory=_library_uow_factory(
                [
                    _library_stub("A", [str(tmp_path / "missing-a")]),
                    _library_stub("B", []),  # no paths configured at all
                ],
            ),
        )

        result = await probe.execute()

        assert result.status == ProbeStatus.UNHEALTHY
        assert result.message is not None

    async def test_should_be_unhealthy_when_listing_libraries_raises(self) -> None:
        broken_uow = AsyncMock()
        broken_uow.__aenter__.return_value = broken_uow
        broken_uow.__aexit__.return_value = None
        broken_uow.libraries = AsyncMock()
        broken_uow.libraries.find_all.side_effect = RuntimeError("DB down")

        probe = FilesystemProbe(library_uow_factory=MagicMock(return_value=broken_uow))

        result = await probe.execute()

        assert result.status == ProbeStatus.UNHEALTHY
        assert result.message is not None
        assert "DB down" in result.message
