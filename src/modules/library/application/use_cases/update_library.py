"""UpdateLibraryUseCase."""

from typing import Any

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.library.application.dtos.library_dtos import (
    LibraryOutput,
    UpdateLibraryInput,
)
from src.modules.library.application.use_cases._to_output import library_to_output
from src.modules.library.application.use_cases.create_library import _build_settings
from src.modules.library.domain.repositories.library_repository import LibraryRepository
from src.modules.library.domain.value_objects.library_id import LibraryId
from src.modules.library.domain.value_objects.library_name import LibraryName
from src.modules.library.domain.value_objects.library_type import LibraryType
from src.modules.library.domain.value_objects.metadata_provider import (
    MetadataProvider,
    MetadataProviderConfig,
)
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.language_code import LanguageCode


class UpdateLibraryUseCase:
    """Partially update an existing library."""

    def __init__(self, library_repository: LibraryRepository) -> None:
        self._repo = library_repository

    async def execute(self, input_dto: UpdateLibraryInput) -> LibraryOutput:
        """Apply partial updates to a library.

        Only fields present (not ``None``) in the input are changed;
        the rest keep their current value via ``entity.with_updates``.

        Args:
            input_dto: The update payload.

        Returns:
            The updated ``LibraryOutput``.

        Raises:
            ResourceNotFoundException: If the library doesn't exist.
        """
        library_id = LibraryId(input_dto.library_id)
        entity = await self._repo.find_by_id(library_id)
        if entity is None:
            raise ResourceNotFoundException.for_resource(
                "Library",
                input_dto.library_id,
            )

        updates: dict[str, Any] = {}
        if input_dto.name is not None:
            updates["name"] = LibraryName(input_dto.name)
        if input_dto.library_type is not None:
            updates["library_type"] = LibraryType(input_dto.library_type)
        if input_dto.paths is not None:
            updates["paths"] = [FilePath(p) for p in input_dto.paths]
        if input_dto.language is not None:
            updates["language"] = LanguageCode(input_dto.language)
        if input_dto.metadata_providers is not None:
            updates["metadata_providers"] = [
                MetadataProviderConfig(
                    provider=MetadataProvider(p["provider"]),
                    priority=p.get("priority", 1),
                    enabled=p.get("enabled", True),
                )
                for p in input_dto.metadata_providers
            ]
        if input_dto.scan_schedule is not None:
            updates["scan_schedule"] = input_dto.scan_schedule
        if input_dto.settings is not None:
            updates["settings"] = _build_settings(input_dto.settings)

        updated = entity.with_updates(**updates)
        saved = await self._repo.save(updated)
        return library_to_output(saved)


__all__ = ["UpdateLibraryUseCase"]
