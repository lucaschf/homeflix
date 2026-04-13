"""Shared entity → output DTO converter for Library use cases."""

from src.modules.library.application.dtos.library_dtos import (
    LibraryOutput,
    LibrarySettingsOutput,
    MetadataProviderOutput,
)
from src.modules.library.domain.entities.library import Library


def library_to_output(entity: Library) -> LibraryOutput:
    """Convert a Library domain entity to its output DTO."""
    return LibraryOutput(
        id=str(entity.id),
        name=entity.name.value,
        library_type=entity.library_type.value,
        paths=[p.value for p in entity.paths],
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
