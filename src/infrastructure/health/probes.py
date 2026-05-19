"""Readiness probes that back ``GET /health/ready``.

The route used to return hardcoded ``healthy`` strings — a stale
placeholder from when the admin panel still needed *something* to
render against. This module replaces them with real checks:

- :class:`DatabaseProbe` runs ``SELECT 1`` so an unreachable DB
  surfaces as ``unhealthy`` rather than a silent green dot.
- :class:`FilesystemProbe` walks every library's configured paths
  and asserts each one exists + is a directory — a typical "mount
  dropped" or "drive unplugged" outage shows up here.

Each probe is a small async callable returning a frozen
:class:`ProbeResult` so the route can mix-and-match probes without
each one knowing about the response envelope.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory

_logger = logging.getLogger(__name__)


class ProbeStatus(str, Enum):
    """Three-state outcome of a single probe."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of a single probe run.

    Attributes:
        name: Short key the route surfaces in ``checks``
            (e.g. ``"database"``, ``"filesystem"``).
        status: Three-state outcome — ``healthy``,
            ``unhealthy``, ``degraded``.
        message: Operator-facing hint when something is wrong
            (e.g. ``"path /mnt/movies missing"``). ``None`` for
            healthy probes.
    """

    name: str
    status: ProbeStatus
    message: str | None = None


class DatabaseProbe:
    """Probe that issues ``SELECT 1`` against the configured session.

    Wraps any error from the driver as ``unhealthy`` with the
    exception message captured. Connection-pool timeouts, missing
    tables and revoked credentials all manifest here.
    """

    name = "database"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def execute(self) -> ProbeResult:
        """Return the probe result; never raises."""
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:  # probes must not bubble up
            _logger.warning("Database probe failed: %s", exc)
            return ProbeResult(
                name=self.name,
                status=ProbeStatus.UNHEALTHY,
                message=f"{type(exc).__name__}: {exc}",
            )
        return ProbeResult(name=self.name, status=ProbeStatus.HEALTHY)


class FilesystemProbe:
    """Probe that walks every library's configured paths.

    ``healthy``: every path on every library resolves to an
    existing directory.
    ``degraded``: at least one library is fully fine but at least
    one other library has a missing / inaccessible path. Catalog
    keeps working for the OK libraries; the broken one will fail
    on next scan.
    ``unhealthy``: every library has at least one bad path, or
    listing libraries itself raises (DB layer broken).
    """

    name = "filesystem"

    def __init__(self, library_uow_factory: LibraryUnitOfWorkFactory) -> None:
        self._library_uow_factory = library_uow_factory

    async def execute(self) -> ProbeResult:
        """Return the probe result; never raises."""
        try:
            async with self._library_uow_factory() as uow:
                libraries = await uow.libraries.find_all()
        except Exception as exc:  # probes must not bubble up
            _logger.warning("Filesystem probe failed listing libraries: %s", exc)
            return ProbeResult(
                name=self.name,
                status=ProbeStatus.UNHEALTHY,
                message=f"{type(exc).__name__}: {exc}",
            )

        if not libraries:
            # No libraries configured yet — nothing to probe, but
            # that's a fresh install, not a fault. Report healthy
            # so the operator's admin Health page doesn't light up
            # red before they've finished setup.
            return ProbeResult(name=self.name, status=ProbeStatus.HEALTHY)

        broken: list[str] = []
        ok_libraries = 0
        for library in libraries:
            paths = list(library.paths)
            if not paths:
                broken.append(f"{library.name}: no paths configured")
                continue
            missing = [p for p in paths if not _path_is_readable_dir(p.value)]
            if missing:
                broken.append(
                    f"{library.name}: missing {', '.join(p.value for p in missing)}",
                )
            else:
                ok_libraries += 1

        if not broken:
            return ProbeResult(name=self.name, status=ProbeStatus.HEALTHY)

        # At least one library is fine — degraded; otherwise hard
        # unhealthy.
        status = ProbeStatus.DEGRADED if ok_libraries > 0 else ProbeStatus.UNHEALTHY
        return ProbeResult(
            name=self.name,
            status=status,
            message="; ".join(broken),
        )


def _path_is_readable_dir(path: str) -> bool:
    """Return ``True`` iff ``path`` resolves to an existing directory.

    Catches every ``OSError`` (permission denied, broken symlink,
    network mount timeout) so the probe stays deterministic.
    """
    try:
        return Path(path).is_dir()
    except OSError:
        return False


__all__ = ["DatabaseProbe", "FilesystemProbe", "ProbeResult", "ProbeStatus"]
