"""Shared entity → output DTO converter for Library use cases."""

from src.modules.library.application.dtos.library_dtos import (
    LibraryOutput,
    LibrarySettingsOutput,
    MetadataProviderOutput,
)
from src.modules.library.domain.entities.library import Library


def library_to_output(
    entity: Library,
    *,
    movie_count: int,
    series_count: int,
) -> LibraryOutput:
    """Project a ``Library`` entity into the transport DTO.

    Pure: no IO, no port dependency. Callers are expected to resolve
    ``movie_count`` / ``series_count`` via ``MediaCountQueryPort``
    beforehand and pass them in. Keeping the mapper pure lets every
    use case decide how to batch (or not) the count queries without
    leaking that choice into the projection.
    """
    paths = [p.value for p in entity.paths]
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
        scan_schedule=entity.scan_schedule.value if entity.scan_schedule else None,
        last_scan_at=entity.last_scan_at.isoformat() if entity.last_scan_at else None,
        movie_count=movie_count,
        series_count=series_count,
        settings=LibrarySettingsOutput(
            generate_thumbnails=entity.settings.generate_thumbnails,
            detect_intros=entity.settings.detect_intros,
            auto_refresh_metadata=entity.settings.auto_refresh_metadata,
        ),
    )


__all__ = ["library_to_output"]
