"""SQLAlchemy implementation of SeriesRepository."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.media.entities import Episode, Season, Series
from src.domain.media.repositories import SeriesRepository
from src.domain.media.value_objects import EpisodeId, FilePath, SeasonId, SeriesId
from src.infrastructure.persistence.mappers import EpisodeMapper, SeasonMapper, SeriesMapper
from src.infrastructure.persistence.models import EpisodeModel, SeasonModel, SeriesModel


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
            .options(
                selectinload(SeriesModel.seasons).selectinload(SeasonModel.episodes),
            )
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
            .options(
                selectinload(SeriesModel.seasons).selectinload(SeasonModel.episodes),
            )
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
        return True

    async def list_all(self) -> Sequence[Series]:
        """List all series (excluding soft-deleted, includes seasons and episodes).

        Returns:
            Sequence of all series ordered by title.
        """
        stmt = (
            select(SeriesModel)
            .where(SeriesModel.deleted_at.is_(None))
            .options(
                selectinload(SeriesModel.seasons).selectinload(SeasonModel.episodes),
            )
            .order_by(SeriesModel.title)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [SeriesMapper.to_entity(model) for model in models]

    async def find_by_file_path(self, file_path: FilePath) -> Series | None:
        """Find a series containing an episode with this file path (excluding soft-deleted).

        Args:
            file_path: The absolute file path.

        Returns:
            The Series if found, None otherwise.
        """
        # Find episode with this file path (not soft-deleted)
        episode_stmt = select(EpisodeModel).where(
            EpisodeModel.file_path == str(file_path),
            EpisodeModel.deleted_at.is_(None),
        )
        episode_result = await self._session.execute(episode_stmt)
        episode_model = episode_result.scalar_one_or_none()

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
        series_id = series.id if series.id is not None else SeriesId.generate()

        updated_seasons: list[Season] = []
        for season in series.seasons:
            season_id = season.id if season.id is not None else SeasonId.generate()

            updated_episodes: list[Episode] = []
            for episode in season.episodes:
                updated_episodes.append(
                    episode.with_updates(
                        id=episode.id if episode.id is not None else EpisodeId.generate(),
                        series_id=series_id,
                    )
                )

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
