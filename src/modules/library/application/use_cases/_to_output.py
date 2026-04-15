"""Shared entity → output DTO converter for Library use cases."""

from src.modules.library.application.dtos.library_dtos import (
    LibraryOutput,
    LibrarySettingsOutput,
    MetadataProviderOutput,
)
from src.modules.library.domain.entities.library import Library
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository


async def library_to_output(
    entity: Library,
    movie_repository: MovieRepository,
    series_repository: SeriesRepository,
) -> LibraryOutput:
    """Convert a Library domain entity to its output DTO.

    The movie/series counts are computed inline from the media repos
    — two ``COUNT(*)`` style queries per library. This is fine for
    tens of libraries; batching across libraries would only matter
    at a scale we don't have today.
    """
    paths = [p.value for p in entity.paths]
    movie_count = await movie_repository.count_under_paths(paths)
    series_count = await series_repository.count_under_paths(paths)
    return LibraryOutput(
        id=str(entity.id),
        name=entity.name.value,
        library_type=entity.library_type.value,
        paths=paths,
        language=entity.language.value,
        metadata_providers=[
            MetadataProviderOutput(
                provider=p.provider.value,
                priority=p.priority,
                enabled=p.enabled,
            )
            for p in entity.metadata_providers
        ],
        scan_schedule=entity.scan_schedule,
        last_scan_at=entity.last_scan_at.isoformat() if entity.last_scan_at else None,
        movie_count=movie_count,
        series_count=series_count,
        settings=LibrarySettingsOutput(
            preferred_audio_language=entity.settings.preferred_audio_language.value,
            preferred_subtitle_language=(
                entity.settings.preferred_subtitle_language.value
                if entity.settings.preferred_subtitle_language
                else None
            ),
            subtitle_mode=entity.settings.subtitle_mode.value,
            generate_thumbnails=entity.settings.generate_thumbnails,
            detect_intros=entity.settings.detect_intros,
            auto_refresh_metadata=entity.settings.auto_refresh_metadata,
        ),
    )


__all__ = ["library_to_output"]
