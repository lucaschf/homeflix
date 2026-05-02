"""Mapper between Movie domain entity and MovieModel ORM model."""

import json

from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects import (
    Collection,
    ContentRating,
    Duration,
    FilePath,
    Genre,
    ImageUrl,
    ImdbId,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    TmdbId,
    Year,
)
from src.modules.media.infrastructure.persistence.mappers.cast_serialization import (
    deserialize_cast,
    serialize_cast,
)
from src.modules.media.infrastructure.persistence.mappers.media_file_mapper import (
    MediaFileMapper,
)
from src.modules.media.infrastructure.persistence.models import MediaFileModel, MovieModel


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

        Creates MediaFileModel instances for each file variant and
        attaches them via the file_variants relationship.

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
        model = MovieModel(
            external_id=str(entity.id),
            title=entity.title.value,
            original_title=entity.original_title.value if entity.original_title else None,
            year=entity.year.value,
            duration=entity.duration.value,
            synopsis=entity.synopsis,
            tagline=entity.tagline,
            poster_path=entity.poster_path.value if entity.poster_path else None,
            backdrop_path=entity.backdrop_path.value if entity.backdrop_path else None,
            logo_path=entity.logo_path.value if entity.logo_path else None,
            scrub_preview_path=entity.scrub_preview_path.value
            if entity.scrub_preview_path
            else None,
            genres=",".join(g.value for g in entity.genres) if entity.genres else None,
            cast=serialize_cast(entity.cast),
            directors=json.dumps(entity.directors, ensure_ascii=False)
            if entity.directors
            else None,
            writers=json.dumps(entity.writers, ensure_ascii=False) if entity.writers else None,
            content_rating=entity.content_rating.value if entity.content_rating else None,
            trailer_url=entity.trailer_url,
            collection_tmdb_id=entity.collection.tmdb_id if entity.collection else None,
            collection_name=entity.collection.name if entity.collection else None,
            collection_parts_count=entity.collection.parts_count if entity.collection else None,
            localized=json.dumps(entity.localized, ensure_ascii=False)
            if entity.localized
            else None,
            file_path=primary.file_path.value if primary else None,
            file_size=primary.file_size if primary else None,
            resolution=primary.resolution.value if primary else None,
            tmdb_id=entity.tmdb_id.value if entity.tmdb_id else None,
            imdb_id=entity.imdb_id.value if entity.imdb_id else None,
        )

        for file in entity.files:
            model.file_variants.append(MediaFileMapper.to_model(file))

        return model

    @staticmethod
    def to_entity(model: MovieModel, *, include_files: bool = True) -> Movie:
        """Convert MovieModel to Movie entity.

        Uses the file_variants relationship if loaded, otherwise
        falls back to flat columns for backward compatibility.

        Args:
            model: The SQLAlchemy MovieModel.
            include_files: When ``False``, skip the file_variants
                relationship entirely and return an entity with
                ``files=[]``. Used by the search path which only
                reads root metadata (title, year, poster, ...) and
                doesn't need the variants — touching ``file_variants``
                on an unloaded relationship would trigger an async
                lazy-load outside the session greenlet.

        Returns:
            Domain Movie entity with reconstructed value objects.
        """
        genre_list: list[Genre] = []
        if model.genres:
            genre_list = [Genre(g.strip()) for g in model.genres.split(",") if g.strip()]

        files: list[MediaFile] = []
        if include_files:
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

        collection = None
        if (
            model.collection_tmdb_id is not None
            and model.collection_name
            and model.collection_parts_count is not None
        ):
            collection = Collection(
                tmdb_id=model.collection_tmdb_id,
                name=model.collection_name,
                parts_count=model.collection_parts_count,
            )

        return Movie(
            id=MovieId(model.external_id),
            title=Title(model.title),
            original_title=Title(model.original_title) if model.original_title else None,
            year=Year(model.year),
            duration=Duration(model.duration),
            synopsis=model.synopsis,
            tagline=model.tagline,
            poster_path=ImageUrl(model.poster_path) if model.poster_path else None,
            backdrop_path=ImageUrl(model.backdrop_path) if model.backdrop_path else None,
            logo_path=ImageUrl(model.logo_path) if model.logo_path else None,
            scrub_preview_path=ImageUrl(model.scrub_preview_path)
            if model.scrub_preview_path
            else None,
            genres=genre_list,
            cast=deserialize_cast(model.cast),
            directors=json.loads(model.directors) if model.directors else [],
            writers=json.loads(model.writers) if model.writers else [],
            content_rating=ContentRating(model.content_rating) if model.content_rating else None,
            trailer_url=model.trailer_url,
            collection=collection,
            localized=json.loads(model.localized) if model.localized else {},
            files=files,
            tmdb_id=TmdbId(model.tmdb_id) if model.tmdb_id else None,
            imdb_id=ImdbId(model.imdb_id) if model.imdb_id else None,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: MovieModel, entity: Movie) -> MovieModel:
        """Update existing MovieModel with entity data.

        Synchronizes file_variants: adds new, updates existing,
        removes absent (by file_path matching).

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
        model.tagline = entity.tagline
        model.poster_path = entity.poster_path.value if entity.poster_path else None
        model.backdrop_path = entity.backdrop_path.value if entity.backdrop_path else None
        model.logo_path = entity.logo_path.value if entity.logo_path else None
        model.scrub_preview_path = (
            entity.scrub_preview_path.value if entity.scrub_preview_path else None
        )
        model.genres = ",".join(g.value for g in entity.genres) if entity.genres else None
        model.cast = serialize_cast(entity.cast)
        model.directors = (
            json.dumps(entity.directors, ensure_ascii=False) if entity.directors else None
        )
        model.writers = json.dumps(entity.writers, ensure_ascii=False) if entity.writers else None
        model.content_rating = entity.content_rating.value if entity.content_rating else None
        model.trailer_url = entity.trailer_url
        model.collection_tmdb_id = entity.collection.tmdb_id if entity.collection else None
        model.collection_name = entity.collection.name if entity.collection else None
        model.collection_parts_count = entity.collection.parts_count if entity.collection else None
        model.localized = (
            json.dumps(entity.localized, ensure_ascii=False) if entity.localized else None
        )
        model.file_path = primary.file_path.value if primary else None
        model.file_size = primary.file_size if primary else None
        model.resolution = primary.resolution.value if primary else None
        model.tmdb_id = entity.tmdb_id.value if entity.tmdb_id else None
        model.imdb_id = entity.imdb_id.value if entity.imdb_id else None

        _sync_file_variants(model.file_variants, entity.files)

        return model


def _sync_file_variants(
    existing_models: list[MediaFileModel],
    entity_files: list[MediaFile],
) -> None:
    """Synchronize ORM file_variants list with entity files.

    Matches by file_path: updates existing, adds new, removes absent.

    Args:
        existing_models: The ORM relationship list (mutable).
        entity_files: The domain MediaFile list (source of truth).
    """
    existing_by_path = {m.file_path: m for m in existing_models}
    entity_paths = {f.file_path.value for f in entity_files}

    # Update existing or add new
    for file in entity_files:
        path = file.file_path.value
        if path in existing_by_path:
            MediaFileMapper.update_model(existing_by_path[path], file)
        else:
            existing_models.append(MediaFileMapper.to_model(file))

    # Remove absent
    to_remove = [m for m in existing_models if m.file_path not in entity_paths]
    for m in to_remove:
        existing_models.remove(m)


__all__ = ["MovieMapper"]
