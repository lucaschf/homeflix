"""Mapper between Series/Season/Episode entities and ORM models."""

import json

from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.value_objects import (
    AirDate,
    Duration,
    EpisodeId,
    FilePath,
    Genre,
    ImageUrl,
    ImdbId,
    MediaFile,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
    TmdbId,
    Year,
)
from src.modules.media.infrastructure.persistence.mappers.media_file_mapper import (
    MediaFileMapper,
)
from src.modules.media.infrastructure.persistence.models import (
    EpisodeModel,
    MediaFileModel,
    SeasonModel,
    SeriesModel,
)


class EpisodeMapper:
    """Bidirectional mapper between Episode entity and EpisodeModel."""

    @staticmethod
    def to_model(entity: Episode, season_id: int) -> EpisodeModel:
        """Convert Episode entity to EpisodeModel.

        Creates MediaFileModel instances for each file variant and
        attaches them via the file_variants relationship.

        Args:
            entity: The domain Episode entity.
            season_id: The internal database ID of the parent season.

        Returns:
            SQLAlchemy EpisodeModel ready for persistence.

        Raises:
            ValueError: If entity has no ID.
        """
        if entity.id is None:
            raise ValueError("Cannot map entity without ID to model")

        primary = entity.primary_file
        model = EpisodeModel(
            external_id=str(entity.id),
            season_id=season_id,
            series_external_id=str(entity.series_id),
            season_number=entity.season_number,
            episode_number=entity.episode_number,
            title=entity.title.value,
            synopsis=entity.synopsis,
            duration=entity.duration.value,
            file_path=primary.file_path.value if primary else None,
            file_size=primary.file_size if primary else None,
            resolution=primary.resolution.value if primary else None,
            thumbnail_path=entity.thumbnail_path.value if entity.thumbnail_path else None,
            air_date=entity.air_date.value if entity.air_date else None,
        )

        for file in entity.files:
            model.file_variants.append(MediaFileMapper.to_model(file))

        return model

    @staticmethod
    def to_entity(model: EpisodeModel) -> Episode:
        """Convert EpisodeModel to Episode entity.

        Uses the file_variants relationship if loaded, otherwise
        falls back to flat columns for backward compatibility.

        Args:
            model: The SQLAlchemy EpisodeModel.

        Returns:
            Domain Episode entity with reconstructed value objects.
        """
        files: list[MediaFile] = []
        if model.file_variants:
            files = [
                MediaFileMapper.to_entity(fv) for fv in model.file_variants if not fv.is_deleted
            ]
        elif model.file_path:
            files = [
                MediaFile(
                    file_path=FilePath(model.file_path),
                    file_size=model.file_size,
                    resolution=Resolution(model.resolution),
                    is_primary=True,
                )
            ]

        return Episode(
            id=EpisodeId(model.external_id),
            series_id=SeriesId(model.series_external_id),
            season_number=model.season_number,
            episode_number=model.episode_number,
            title=Title(model.title),
            synopsis=model.synopsis,
            duration=Duration(model.duration),
            files=files,
            thumbnail_path=ImageUrl(model.thumbnail_path) if model.thumbnail_path else None,
            air_date=AirDate(model.air_date) if model.air_date else None,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: EpisodeModel, entity: Episode) -> EpisodeModel:
        """Update existing EpisodeModel with entity data.

        Synchronizes file_variants with entity files.

        Args:
            model: The existing SQLAlchemy EpisodeModel.
            entity: The domain Episode entity with updated data.

        Returns:
            The updated EpisodeModel.
        """
        primary = entity.primary_file
        model.season_number = entity.season_number
        model.episode_number = entity.episode_number
        model.title = entity.title.value
        model.synopsis = entity.synopsis
        model.duration = entity.duration.value
        model.file_path = primary.file_path.value if primary else None
        model.file_size = primary.file_size if primary else None
        model.resolution = primary.resolution.value if primary else None
        model.thumbnail_path = entity.thumbnail_path.value if entity.thumbnail_path else None
        model.air_date = entity.air_date.value if entity.air_date else None

        _sync_episode_file_variants(model.file_variants, entity.files)

        return model


class SeasonMapper:
    """Bidirectional mapper between Season entity and SeasonModel."""

    @staticmethod
    def to_model(entity: Season, series_db_id: int) -> SeasonModel:
        """Convert Season entity to SeasonModel.

        Args:
            entity: The domain Season entity.
            series_db_id: The internal database ID of the parent series.

        Returns:
            SQLAlchemy SeasonModel ready for persistence (without episodes).

        Raises:
            ValueError: If entity has no ID.
        """
        if entity.id is None:
            raise ValueError("Cannot map entity without ID to model")

        return SeasonModel(
            external_id=str(entity.id),
            series_id=series_db_id,
            series_external_id=str(entity.series_id),
            season_number=entity.season_number,
            title=entity.title.value if entity.title else None,
            synopsis=entity.synopsis,
            poster_path=entity.poster_path.value if entity.poster_path else None,
            air_date=entity.air_date.value if entity.air_date else None,
        )

    @staticmethod
    def to_entity(model: SeasonModel, *, include_episodes: bool = True) -> Season:
        """Convert SeasonModel to Season entity.

        Args:
            model: The SQLAlchemy SeasonModel.
            include_episodes: Whether to include episodes in the entity.

        Returns:
            Domain Season entity with reconstructed value objects.
        """
        episode_list: list[Episode] = []
        if include_episodes and model.episodes:
            episode_list = [
                EpisodeMapper.to_entity(ep) for ep in model.episodes if not ep.is_deleted
            ]

        return Season(
            id=SeasonId(model.external_id),
            series_id=SeriesId(model.series_external_id),
            season_number=model.season_number,
            title=Title(model.title) if model.title else None,
            synopsis=model.synopsis,
            poster_path=ImageUrl(model.poster_path) if model.poster_path else None,
            air_date=AirDate(model.air_date) if model.air_date else None,
            episodes=episode_list,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: SeasonModel, entity: Season) -> SeasonModel:
        """Update existing SeasonModel with entity data.

        Args:
            model: The existing SQLAlchemy SeasonModel.
            entity: The domain Season entity with updated data.

        Returns:
            The updated SeasonModel.
        """
        model.season_number = entity.season_number
        model.title = entity.title.value if entity.title else None
        model.synopsis = entity.synopsis
        model.poster_path = entity.poster_path.value if entity.poster_path else None
        model.air_date = entity.air_date.value if entity.air_date else None

        return model


class SeriesMapper:
    """Bidirectional mapper between Series aggregate and SeriesModel."""

    @staticmethod
    def to_model(entity: Series) -> SeriesModel:
        """Convert Series entity to SeriesModel.

        Args:
            entity: The domain Series entity.

        Returns:
            SQLAlchemy SeriesModel ready for persistence (without seasons).

        Raises:
            ValueError: If entity has no ID.
        """
        if entity.id is None:
            raise ValueError("Cannot map entity without ID to model")

        return SeriesModel(
            external_id=str(entity.id),
            title=entity.title.value,
            original_title=entity.original_title.value if entity.original_title else None,
            start_year=entity.start_year.value,
            end_year=entity.end_year.value if entity.end_year else None,
            synopsis=entity.synopsis,
            poster_path=entity.poster_path.value if entity.poster_path else None,
            backdrop_path=entity.backdrop_path.value if entity.backdrop_path else None,
            genres=",".join(g.value for g in entity.genres) if entity.genres else None,
            localized=json.dumps(entity.localized, ensure_ascii=False)
            if entity.localized
            else None,
            tmdb_id=entity.tmdb_id.value if entity.tmdb_id else None,
            imdb_id=entity.imdb_id.value if entity.imdb_id else None,
        )

    @staticmethod
    def to_entity(model: SeriesModel, *, include_seasons: bool = True) -> Series:
        """Convert SeriesModel to Series entity.

        Args:
            model: The SQLAlchemy SeriesModel.
            include_seasons: Whether to include seasons (and episodes) in the entity.

        Returns:
            Domain Series entity with reconstructed value objects.
        """
        genre_list: list[Genre] = []
        if model.genres:
            genre_list = [Genre(g.strip()) for g in model.genres.split(",") if g.strip()]

        season_list: list[Season] = []
        if include_seasons and model.seasons:
            season_list = [SeasonMapper.to_entity(s) for s in model.seasons if not s.is_deleted]

        return Series(
            id=SeriesId(model.external_id),
            title=Title(model.title),
            original_title=Title(model.original_title) if model.original_title else None,
            start_year=Year(model.start_year),
            end_year=Year(model.end_year) if model.end_year else None,
            synopsis=model.synopsis,
            poster_path=ImageUrl(model.poster_path) if model.poster_path else None,
            backdrop_path=ImageUrl(model.backdrop_path) if model.backdrop_path else None,
            genres=genre_list,
            localized=json.loads(model.localized) if model.localized else {},
            tmdb_id=TmdbId(model.tmdb_id) if model.tmdb_id else None,
            imdb_id=ImdbId(model.imdb_id) if model.imdb_id else None,
            seasons=season_list,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: SeriesModel, entity: Series) -> SeriesModel:
        """Update existing SeriesModel with entity data.

        Args:
            model: The existing SQLAlchemy SeriesModel.
            entity: The domain Series entity with updated data.

        Returns:
            The updated SeriesModel.
        """
        model.title = entity.title.value
        model.original_title = entity.original_title.value if entity.original_title else None
        model.start_year = entity.start_year.value
        model.end_year = entity.end_year.value if entity.end_year else None
        model.synopsis = entity.synopsis
        model.poster_path = entity.poster_path.value if entity.poster_path else None
        model.backdrop_path = entity.backdrop_path.value if entity.backdrop_path else None
        model.genres = ",".join(g.value for g in entity.genres) if entity.genres else None
        model.localized = (
            json.dumps(entity.localized, ensure_ascii=False) if entity.localized else None
        )
        model.tmdb_id = entity.tmdb_id.value if entity.tmdb_id else None
        model.imdb_id = entity.imdb_id.value if entity.imdb_id else None

        return model


def _sync_episode_file_variants(
    existing_models: list[MediaFileModel],
    entity_files: list[MediaFile],
) -> None:
    """Synchronize ORM file_variants list with entity files.

    Args:
        existing_models: The ORM relationship list (mutable).
        entity_files: The domain MediaFile list (source of truth).
    """
    existing_by_path = {m.file_path: m for m in existing_models}
    entity_paths = {f.file_path.value for f in entity_files}

    for file in entity_files:
        path = file.file_path.value
        if path in existing_by_path:
            MediaFileMapper.update_model(existing_by_path[path], file)
        else:
            existing_models.append(MediaFileMapper.to_model(file))

    to_remove = [m for m in existing_models if m.file_path not in entity_paths]
    for m in to_remove:
        existing_models.remove(m)


__all__ = ["EpisodeMapper", "SeasonMapper", "SeriesMapper"]
