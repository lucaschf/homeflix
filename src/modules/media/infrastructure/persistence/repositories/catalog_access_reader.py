"""SQLAlchemy implementation of CatalogAccessReader."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.repositories import CatalogAccessReader, TitleAccess
from src.modules.media.domain.value_objects import MovieId, SeriesId
from src.modules.media.infrastructure.persistence.mappers._certification import (
    certification_from_columns,
)
from src.modules.media.infrastructure.persistence.models.movie import MovieModel
from src.modules.media.infrastructure.persistence.models.series import SeriesModel
from src.modules.media.infrastructure.persistence.repositories._visibility_filter import (
    CatalogModel,
    visibility_conditions,
)
from src.shared_kernel.content_policy import ViewingPolicy


class SqlAlchemyCatalogAccessReader(CatalogAccessReader):
    """Read title access off the certification columns alone.

    Selects the external id and the three certification columns — no
    entity, no relationship, no mapper — so a series with hundreds of
    episodes costs the same as a movie. Visibility comes only from
    :func:`visibility_conditions`, the projection the rest of the catalog
    shares, and the age is rebuilt by :func:`certification_from_columns`,
    so the empty-label rule matches the funnel and the entity mappers.

    Example:
        >>> reader = SqlAlchemyCatalogAccessReader(session)
        >>> access = await reader.find_movie_access([movie_id], policy=policy)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the reader with a database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    async def find_movie_access(
        self,
        movie_ids: Sequence[MovieId],
        *,
        policy: ViewingPolicy,
    ) -> dict[str, TitleAccess]:
        """Resolve which of these movies the policy permits."""
        return await self._find_access(MovieModel, [str(mid) for mid in movie_ids], policy)

    async def find_series_access(
        self,
        series_ids: Sequence[SeriesId],
        *,
        policy: ViewingPolicy,
    ) -> dict[str, TitleAccess]:
        """Resolve which of these series the policy permits."""
        return await self._find_access(SeriesModel, [str(sid) for sid in series_ids], policy)

    async def _find_access(
        self,
        model: CatalogModel,
        external_ids: Sequence[str],
        policy: ViewingPolicy,
    ) -> dict[str, TitleAccess]:
        """Run the shared column query against one catalog model.

        Args:
            model: The catalog model to query.
            external_ids: Raw external ids to look up.
            policy: The caller's viewing policy.

        Returns:
            Access entries keyed by external id, for permitted rows only.

        Raises:
            TypeError: If ``policy`` is ``None``. Everywhere else in the
                catalog ``None`` means an ungated read, so a caller that
                slips one past the type checker (an untyped mock, a
                ``type: ignore``) would get every title back. Refusing it
                at runtime keeps this reader fail-closed.
        """
        if policy is None:
            raise TypeError("CatalogAccessReader requires a ViewingPolicy; None is not allowed")

        if not external_ids:
            # ``IN ()`` would still round-trip to return nothing.
            return {}

        stmt = select(
            model.external_id,
            model.content_rating,
            model.minimum_age,
            model.rating_system,
        ).where(
            model.external_id.in_(external_ids),
            model.deleted_at.is_(None),
            *visibility_conditions(model, policy),
        )
        result = await self._session.execute(stmt)

        access: dict[str, TitleAccess] = {}
        for row in result:
            certification = certification_from_columns(row)
            access[row.external_id] = TitleAccess(
                minimum_age=certification.minimum_age if certification else None,
            )
        return access


__all__ = ["SqlAlchemyCatalogAccessReader"]
