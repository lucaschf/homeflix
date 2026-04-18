"""Shared entity → output DTO converter for Library use cases."""

from src.modules.library.application.dtos.library_dtos import (
    LibraryOutput,
    LibrarySettingsOutput,
    MetadataProviderOutput,
)
from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.domain.entities.library import Library


async def library_to_output(
    entity: Library,
    media_count_query: MediaCountQueryPort,
) -> LibraryOutput:
    """Convert a Library domain entity to its output DTO.

    The movie/series counts are resolved via the ``MediaCountQueryPort``
    so the Library BC never imports Media repositories directly. See
    ADR-009 for the cross-BC read port pattern.
    """
    paths = [p.value for p in entity.paths]
    movie_count = await media_count_query.count_movies_under_paths(paths)
    series_count = await media_count_query.count_series_under_paths(paths)
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
