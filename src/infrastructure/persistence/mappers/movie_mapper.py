"""Mapper between Movie domain entity and MovieModel ORM model."""

from src.domain.media.entities import Movie
from src.domain.media.value_objects import (
    Duration,
    FilePath,
    Genre,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    Year,
)
from src.infrastructure.persistence.models import MovieModel


class MovieMapper:
    """Bidirectional mapper between Movie entity and MovieModel.

    Handles conversion of value objects to primitive types for storage
    and reconstruction of entities from database records.

    Example:
        >>> model = MovieMapper.to_model(movie)
        >>> entity = MovieMapper.to_entity(model)
    """

    @staticmethod
    def to_model(entity: Movie) -> MovieModel:
        """Convert Movie entity to MovieModel.

        Args:
            entity: The domain Movie entity.

        Returns:
            SQLAlchemy MovieModel ready for persistence.

        Raises:
            ValueError: If entity has no ID.
        """
        if entity.id is None:
            raise ValueError("Cannot map entity without ID to model")

        primary = entity.primary_file
        return MovieModel(
            external_id=str(entity.id),
            title=entity.title.value,
            original_title=entity.original_title.value if entity.original_title else None,
            year=entity.year.value,
            duration=entity.duration.value,
            synopsis=entity.synopsis,
            poster_path=entity.poster_path.value if entity.poster_path else None,
            backdrop_path=entity.backdrop_path.value if entity.backdrop_path else None,
            genres=",".join(g.value for g in entity.genres) if entity.genres else None,
            file_path=primary.file_path.value if primary else None,
            file_size=primary.file_size if primary else None,
            resolution=primary.resolution.value if primary else None,
            tmdb_id=entity.tmdb_id,
            imdb_id=entity.imdb_id,
        )

    @staticmethod
    def to_entity(model: MovieModel) -> Movie:
        """Convert MovieModel to Movie entity.

        Args:
            model: The SQLAlchemy MovieModel.

        Returns:
            Domain Movie entity with reconstructed value objects.
        """
        genre_list: list[Genre] = []
        if model.genres:
            genre_list = [Genre(g.strip()) for g in model.genres.split(",") if g.strip()]

        files: list[MediaFile] = []
        if model.file_path:
            files = [
                MediaFile(
                    file_path=FilePath(model.file_path),
                    file_size=model.file_size,
                    resolution=Resolution(model.resolution),
                    is_primary=True,
                )
            ]

        return Movie(
            id=MovieId(model.external_id),
            title=Title(model.title),
            original_title=Title(model.original_title) if model.original_title else None,
            year=Year(model.year),
            duration=Duration(model.duration),
            synopsis=model.synopsis,
            poster_path=FilePath(model.poster_path) if model.poster_path else None,
            backdrop_path=FilePath(model.backdrop_path) if model.backdrop_path else None,
            genres=genre_list,
            files=files,
            tmdb_id=model.tmdb_id,
            imdb_id=model.imdb_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: MovieModel, entity: Movie) -> MovieModel:
        """Update existing MovieModel with entity data.

        Args:
            model: The existing SQLAlchemy MovieModel.
            entity: The domain Movie entity with updated data.

        Returns:
            The updated MovieModel.
        """
        primary = entity.primary_file
        model.title = entity.title.value
        model.original_title = entity.original_title.value if entity.original_title else None
        model.year = entity.year.value
        model.duration = entity.duration.value
        model.synopsis = entity.synopsis
        model.poster_path = entity.poster_path.value if entity.poster_path else None
        model.backdrop_path = entity.backdrop_path.value if entity.backdrop_path else None
        model.genres = ",".join(g.value for g in entity.genres) if entity.genres else None
        model.file_path = primary.file_path.value if primary else None
        model.file_size = primary.file_size if primary else None
        model.resolution = primary.resolution.value if primary else None
        model.tmdb_id = entity.tmdb_id
        model.imdb_id = entity.imdb_id

        return model


__all__ = ["MovieMapper"]
