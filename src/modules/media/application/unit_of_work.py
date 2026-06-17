"""Media bounded-context Unit of Work interface.

Exposes the repositories that participate in a single media transaction.
Concrete implementations live in the infrastructure layer; use cases
depend only on this abstraction so they stay framework-agnostic.
"""

from abc import ABC, abstractmethod

from src.building_blocks.application.unit_of_work import UnitOfWork
from src.modules.media.domain.repositories import (
    IntroDetectionRunRepository,
    MediaConflictRepository,
    MovieRepository,
    ScanRunRepository,
    SeriesRepository,
)


class MediaUnitOfWork(UnitOfWork):
    """Transactional boundary covering every media-side repository.

    Spans movies, series, scan runs, and media conflicts so writes
    across those aggregates share one transaction. Subclasses populate
    the repository attributes on ``__aenter__``; outside the context
    manager the attributes are not guaranteed to exist — accessing
    them raises ``AttributeError``, which surfaces misuse at the call
    site instead of silently operating against a stale or foreign
    session.
    """

    movies: MovieRepository
    series: SeriesRepository
    scan_runs: ScanRunRepository
    intro_detection_runs: IntroDetectionRunRepository
    media_conflicts: MediaConflictRepository


class MediaUnitOfWorkFactory(ABC):
    """Builds fresh ``MediaUnitOfWork`` instances on demand.

    Use cases depend on this factory rather than a single UoW so they
    can open a new transaction per business operation. A scan that
    processes thousands of files, for example, opens one UoW per file
    group — a failure on one file rolls back only that group, not the
    whole scan.
    """

    @abstractmethod
    def __call__(self) -> MediaUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""


__all__ = ["MediaUnitOfWork", "MediaUnitOfWorkFactory"]
