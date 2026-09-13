"""Catalog access role interface (ADR-033, ADR-035).

The narrow contract a caller depends on when all it needs to know about a
title is whether a viewing policy lets a profile reach it, and at what
age. ``watch_progress`` and ``collections`` ask that on every request — a
progress autosave, a watchlist toggle — and loading the aggregate to
answer it would hydrate every season, episode and file variant of a
series only to read one column.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.modules.media.domain.value_objects import MovieId, SeriesId
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.age_rating import AgeRating


@dataclass(frozen=True)
class TitleAccess:
    """What a caller learns about a title the policy lets it reach.

    Attributes:
        minimum_age: The title's normalized minimum age, or ``None`` when
            it carries no determinable certification. ``None`` is not
            "suitable for everyone" — consumers resolve it through
            :meth:`AgeRating.allows`, which reads it as adult.
    """

    minimum_age: AgeRating | None


class CatalogAccessReader(ABC):
    """Answers which titles a viewing policy allows, without loading them.

    ``policy`` is required and never ``None`` on every method. The
    catalog repositories accept ``policy=None`` as the ungated internal
    read, and the visibility funnel renders it as no condition at all; a
    reader whose only purpose is to decide access cannot offer that
    shape, or a forgotten argument would silently grant everything.
    """

    @abstractmethod
    async def find_movie_access(
        self,
        movie_ids: Sequence[MovieId],
        *,
        policy: ViewingPolicy,
    ) -> Mapping[str, TitleAccess]:
        """Resolve which of these movies the policy permits.

        Args:
            movie_ids: The movies to look up. Duplicates are tolerated.
            policy: The caller's viewing policy, applied on both axes.

        Returns:
            One entry per permitted movie, keyed by its external id
            (``mov_xxx``). A movie that does not exist, is soft-deleted,
            or is denied by the policy is absent — the three cases are
            deliberately indistinguishable. Empty when ``movie_ids`` is.
        """
        ...

    @abstractmethod
    async def find_series_access(
        self,
        series_ids: Sequence[SeriesId],
        *,
        policy: ViewingPolicy,
    ) -> Mapping[str, TitleAccess]:
        """Resolve which of these series the policy permits.

        A series is the unit of restriction: its seasons and episodes
        carry no certification of their own (ADR-035, known limitations).

        Args:
            series_ids: The series to look up. Duplicates are tolerated.
            policy: The caller's viewing policy, applied on both axes.

        Returns:
            One entry per permitted series, keyed by its external id
            (``ser_xxx``). A series that does not exist, is soft-deleted,
            or is denied by the policy is absent. Empty when
            ``series_ids`` is.
        """
        ...


__all__ = ["CatalogAccessReader", "TitleAccess"]
