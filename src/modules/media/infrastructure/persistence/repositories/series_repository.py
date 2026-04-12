"""SQLAlchemy implementation of SeriesRepository."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.building_blocks.application.pagination import (
    PaginatedResult,
    Pagination,
    decode_cursor,
    encode_cursor,
)
from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.repositories import SeriesRepository
from src.modules.media.domain.repositories.movie_repository import GenreRow
from src.modules.media.domain.value_objects import (
    EpisodeId,
    FilePath,
    Genre,
    SeasonId,
    SeriesId,
    Title,
)
from src.modules.media.infrastructure.persistence.mappers import (
    EpisodeMapper,
    SeasonMapper,
    SeriesMapper,
)
from src.modules.media.infrastructure.persistence.models import (
    EpisodeModel,
    MediaFileModel,
    SeasonModel,
    SeriesModel,
)
from src.modules.media.infrastructure.persistence.repositories._genre_helpers import (
    fetch_genre_paginated_page,
    fetch_genre_rows,
)


class SQLAlchemySeriesRepository(SeriesRepository):
    """SQLAlchemy implementation of SeriesRepository.

    Provides async database operations for Series aggregates,
    including nested seasons and episodes.

    Example:
        >>> repo = SQLAlchemySeriesRepository(session)
        >>> series = await repo.find_by_id(SeriesId("ser_abc123"))
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    @staticmethod
    def _series_load_options() -> list[Any]:
        """Return common eager-loading options for series queries."""
        return [
            selectinload(SeriesModel.seasons)
            .selectinload(SeasonModel.episodes)
            .selectinload(EpisodeModel.file_variants),
        ]

    async def find_by_id(self, series_id: SeriesId) -> Series | None:
        """Find a series by its ID (includes seasons and episodes).

        Args:
            series_id: The series' external ID.

        Returns:
            The Series if found, None otherwise.
        """
        stmt = (
            select(SeriesModel)
            .where(
                SeriesModel.external_id == str(series_id),
                SeriesModel.deleted_at.is_(None),
            )
            .options(*self._series_load_options())
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return None if model is None else SeriesMapper.to_entity(model)

    async def save(self, series: Series) -> Series:
        """Persist a series with all its seasons and episodes.

        Args:
            series: The series to save.

        Returns:
            The saved series (with generated IDs if new).
        """
        # Generate IDs for entities that don't have them
        series = self._ensure_ids(series)

        # Check if series already exists (load seasons for update)
        stmt = (
            select(SeriesModel)
            .where(SeriesModel.external_id == str(series.id))
            .options(*self._series_load_options())
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(stmt)
        existing_model = result.scalar_one_or_none()

        if existing_model is not None:
            # Restore if soft-deleted (including children)
            if existing_model.is_deleted:
                existing_model.restore()
                for season in existing_model.seasons:
                    season.restore()
                    for episode in season.episodes:
                        episode.restore()

            return await self._update_series(existing_model, series)

        return await self._create_series(series)

    async def delete(self, series_id: SeriesId) -> bool:
        """Soft delete a series and all its seasons/episodes.

        Args:
            series_id: The series' external ID.

        Returns:
            True if deleted, False if not found.
        """
        stmt = (
            select(SeriesModel)
            .where(
                SeriesModel.external_id == str(series_id),
                SeriesModel.deleted_at.is_(None),
            )
            .options(
                selectinload(SeriesModel.seasons).selectinload(SeasonModel.episodes),
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        # Soft delete series and all children
        model.soft_delete()
        for season in model.seasons:
            season.soft_delete()
            for episode in season.episodes:
                episode.soft_delete()

        await self._session.flush()
        await self._session.commit()
        return True

    async def list_all(self) -> Sequence[Series]:
        """List all series (excluding soft-deleted, includes seasons and episodes).

        Returns:
            Sequence of all series ordered by title.
        """
        stmt = (
            select(SeriesModel)
            .where(SeriesModel.deleted_at.is_(None))
            .options(*self._series_load_options())
            .order_by(SeriesModel.title)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [SeriesMapper.to_entity(model) for model in models]

    async def list_paginated(
        self,
        cursor: str | None,
        limit: int,
        *,
        include_total: bool = False,
    ) -> PaginatedResult[Series]:
        """List series in a single cursor-paginated page.

        Sorted by ``id DESC`` so the most recently inserted rows appear
        first — see the building-block docstring and the matching
        ``MovieRepository.list_paginated`` for the full justification.
        Soft-deleted rows are filtered out the same way as ``list_all``.
        Fetches ``limit + 1`` rows to detect ``has_more`` cheaply
        without an extra query. The full season / episode hierarchy is
        loaded via the same options as ``list_all``; if that turns out
        to be a perf issue we'll add a shallow variant later.
        """
        decoded = decode_cursor(cursor)

        stmt = (
            select(SeriesModel)
            .where(SeriesModel.deleted_at.is_(None))
            .options(*self._series_load_options())
        )

        if decoded is not None:
            stmt = stmt.where(SeriesModel.id < decoded.id)

        stmt = stmt.order_by(SeriesModel.id.desc()).limit(limit + 1)

        result = await self._session.execute(stmt)
        models = list(result.scalars().all())

        has_more = len(models) > limit
        if has_more:
            models = models[:limit]

        next_cursor: str | None = None
        if has_more and models:
            next_cursor = encode_cursor(models[-1].id)

        total_count: int | None = None
        if include_total:
            count_stmt = (
                select(func.count())
                .select_from(SeriesModel)
                .where(SeriesModel.deleted_at.is_(None))
            )
            total_count = (await self._session.execute(count_stmt)).scalar_one()

        return PaginatedResult(
            items=[SeriesMapper.to_entity(m) for m in models],
            pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
            total_count=total_count,
        )

    async def list_genre_rows(self, lang: str) -> Sequence[GenreRow]:
        """Project the genre columns of every non-deleted series row."""
        return await fetch_genre_rows(self._session, SeriesModel, lang)

    async def list_paginated_by_genre(
        self,
        genre: Genre,
        cursor: str | None,
        limit: int,
    ) -> PaginatedResult[Series]:
        """List series for a single genre, paginated and sorted by title.

        Delegates the SQL boilerplate to the shared
        ``fetch_genre_paginated_page`` helper so this method and its
        movie counterpart stay in lockstep. The full season / episode
        hierarchy is loaded via the existing ``_series_load_options``
        because consumers may want to render episode counts on the
        carousel card.
        """
        return await fetch_genre_paginated_page(
            session=self._session,
            model=SeriesModel,
            mapper_to_entity=SeriesMapper.to_entity,
            options=list(self._series_load_options()),
            genre=genre,
            cursor=cursor,
            limit=limit,
        )

    async def find_random(self, limit: int, *, with_backdrop: bool = False) -> Sequence[Series]:
        """Return random series."""
        from sqlalchemy.sql.expression import func

        stmt = (
            select(SeriesModel)
            .where(SeriesModel.deleted_at.is_(None))
            .options(*self._series_load_options())
        )
        if with_backdrop:
            stmt = stmt.where(
                SeriesModel.backdrop_path.is_not(None),
                SeriesModel.backdrop_path != "",
            )
        stmt = stmt.order_by(func.random()).limit(limit)
        result = await self._session.execute(stmt)
        return [SeriesMapper.to_entity(m) for m in result.scalars().all()]

    async def find_by_title(self, title: Title) -> Series | None:
        """Find a series by its title (case-insensitive).

        Args:
            title: The series title to search for.

        Returns:
            The Series if found, None otherwise.
        """
        stmt = (
            select(SeriesModel)
            .where(
                SeriesModel.title.ilike(title.value),
                SeriesModel.deleted_at.is_(None),
            )
            .options(*self._series_load_options())
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return None if model is None else SeriesMapper.to_entity(model)

    async def find_by_ids(self, series_ids: Sequence[SeriesId]) -> dict[str, Series]:
        """Find multiple series by their IDs in a single query."""
        if not series_ids:
            return {}

        ext_ids = [str(sid) for sid in series_ids]
        stmt = (
            select(SeriesModel)
            .where(
                SeriesModel.external_id.in_(ext_ids),
                SeriesModel.deleted_at.is_(None),
            )
            .options(*self._series_load_options())
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(stmt)
        return {
            model.external_id: SeriesMapper.to_entity(model) for model in result.scalars().all()
        }

    async def find_by_episode_id(self, episode_id: EpisodeId) -> Series | None:
        """Find a series containing an episode with this ID.

        Args:
            episode_id: The episode's external ID.

        Returns:
            The Series if found, None otherwise.
        """
        stmt = select(EpisodeModel).where(
            EpisodeModel.external_id == str(episode_id),
            EpisodeModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        episode_model = result.scalar_one_or_none()

        if episode_model is None:
            return None

        return await self.find_by_id(SeriesId(episode_model.series_external_id))

    async def find_by_file_path(self, file_path: FilePath) -> Series | None:
        """Find a series containing an episode with this file path.

        Searches both the file_variants table and the flat column
        for backward compatibility.

        Args:
            file_path: The absolute file path.

        Returns:
            The Series if found, None otherwise.
        """
        # Search in file_variants table
        stmt = (
            select(EpisodeModel)
            .join(MediaFileModel, MediaFileModel.episode_id == EpisodeModel.id)
            .where(
                MediaFileModel.file_path == str(file_path),
                EpisodeModel.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        episode_model = result.scalar_one_or_none()

        if episode_model is None:
            # Fallback to flat column
            stmt = select(EpisodeModel).where(
                EpisodeModel.file_path == str(file_path),
                EpisodeModel.deleted_at.is_(None),
            )
            result = await self._session.execute(stmt)
            episode_model = result.scalar_one_or_none()

        if episode_model is None:
            return None

        # Load the full series
        return await self.find_by_id(SeriesId(episode_model.series_external_id))

    def _ensure_ids(self, series: Series) -> Series:
        """Ensure all entities have IDs, generating them if needed.

        Args:
            series: The series to process.

        Returns:
            Series with all IDs populated.
        """
        series_id = SeriesId.generate_if_absent(series.id)

        updated_seasons: list[Season] = []
        for season in series.seasons:
            season_id = SeasonId.generate_if_absent(season.id)

            updated_episodes: list[Episode] = []
            for episode in season.episodes:
                episode_id = EpisodeId.generate_if_absent(episode.id)
                updated_episodes.append(episode.with_updates(id=episode_id, series_id=series_id))

            updated_seasons.append(
                season.with_updates(
                    id=season_id,
                    series_id=series_id,
                    episodes=updated_episodes,
                )
            )

        return series.with_updates(id=series_id, seasons=updated_seasons)

    async def _create_series(self, series: Series) -> Series:
        """Create a new series with all seasons and episodes.

        Args:
            series: The series to create.

        Returns:
            The created series.
        """
        # Create series model
        series_model = SeriesMapper.to_model(series)
        self._session.add(series_model)
        await self._session.flush()

        # Create seasons and episodes
        for season in series.seasons:
            season_model = SeasonMapper.to_model(season, series_model.id)
            self._session.add(season_model)
            await self._session.flush()

            for episode in season.episodes:
                episode_model = EpisodeMapper.to_model(episode, season_model.id)
                self._session.add(episode_model)

        await self._session.flush()
        await self._session.commit()

        # Reload and return (series.id is guaranteed to exist after _ensure_ids)
        assert series.id is not None
        result = await self.find_by_id(series.id)
        assert result is not None
        return result

    async def _update_series(
        self,
        existing_model: SeriesModel,
        series: Series,
    ) -> Series:
        """Update existing series with all seasons and episodes.

        Args:
            existing_model: The existing series model.
            series: The series with updated data.

        Returns:
            The updated series.
        """
        # Update series
        SeriesMapper.update_model(existing_model, series)

        # Get existing seasons by external_id
        existing_seasons = {s.external_id: s for s in existing_model.seasons}

        # Update or create seasons
        for season in series.seasons:
            season_ext_id = str(season.id)

            if season_ext_id in existing_seasons:
                season_model = existing_seasons[season_ext_id]
                SeasonMapper.update_model(season_model, season)
                await self._update_season_episodes(season_model, season)
                del existing_seasons[season_ext_id]
            else:
                # New season - add to relationship list
                season_model = SeasonMapper.to_model(season, existing_model.id)
                existing_model.seasons.append(season_model)
                await self._session.flush()

                for episode in season.episodes:
                    episode_model = EpisodeMapper.to_model(episode, season_model.id)
                    self._session.add(episode_model)

        # Soft delete removed seasons and their episodes
        for season_model in existing_seasons.values():
            season_model.soft_delete()
            for ep_model in season_model.episodes:
                ep_model.soft_delete()

        await self._session.flush()
        await self._session.commit()

        # Reload and return (series.id is guaranteed to exist)
        assert series.id is not None
        result = await self.find_by_id(series.id)
        assert result is not None
        return result

    async def _update_season_episodes(
        self,
        season_model: SeasonModel,
        season: Season,
    ) -> None:
        """Update episodes for an existing season.

        Args:
            season_model: The existing season model.
            season: The season with updated episodes.
        """
        existing_episodes = {e.external_id: e for e in season_model.episodes}

        for episode in season.episodes:
            episode_ext_id = str(episode.id)

            if episode_ext_id in existing_episodes:
                EpisodeMapper.update_model(existing_episodes[episode_ext_id], episode)
                del existing_episodes[episode_ext_id]
            else:
                # New episode
                episode_model = EpisodeMapper.to_model(episode, season_model.id)
                self._session.add(episode_model)

        # Soft delete removed episodes
        for episode_model in existing_episodes.values():
            episode_model.soft_delete()


__all__ = ["SQLAlchemySeriesRepository"]
