"""CreateLibraryUseCase."""

from typing import Any

from src.modules.library.application.dtos.library_dtos import (
    CreateLibraryInput,
    LibraryOutput,
)
from src.modules.library.application.use_cases._to_output import library_to_output
from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.repositories.library_repository import LibraryRepository
from src.modules.library.domain.value_objects.library_settings import LibrarySettings
from src.modules.library.domain.value_objects.library_type import LibraryType
from src.modules.library.domain.value_objects.metadata_provider import (
    MetadataProvider,
    MetadataProviderConfig,
)
from src.modules.library.domain.value_objects.subtitle_mode import SubtitleMode
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.shared_kernel.value_objects.language_code import LanguageCode


class CreateLibraryUseCase:
    """Create a new library and persist it."""

    def __init__(
        self,
        library_repository: LibraryRepository,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        self._repo = library_repository
        self._movie_repo = movie_repository
        self._series_repo = series_repository

    async def execute(self, input_dto: CreateLibraryInput) -> LibraryOutput:
        """Create and persist a new Library.

        Args:
            input_dto: Library creation parameters.

        Returns:
            The persisted library as a ``LibraryOutput``.
        """
        providers = [
            MetadataProviderConfig(
                provider=MetadataProvider(p["provider"]),
                priority=p.get("priority", 1),
                enabled=p.get("enabled", True),
            )
            for p in input_dto.metadata_providers
        ]

        settings = _build_settings(input_dto.settings) if input_dto.settings else None

        library = Library.create(
            name=input_dto.name,
            library_type=LibraryType(input_dto.library_type),
            paths=input_dto.paths,
            language=input_dto.language,
            metadata_providers=providers,
            settings=settings,
        )
        if input_dto.scan_schedule:
            library = library.with_updates(scan_schedule=input_dto.scan_schedule)

        saved = await self._repo.save(library)
        return await library_to_output(saved, self._movie_repo, self._series_repo)


def _build_settings(raw: dict[str, Any]) -> LibrarySettings:
    """Build a ``LibrarySettings`` VO from a raw dict.

    Missing keys fall back to the VO's own defaults so callers can
    pass a partial dict (e.g. ``{"subtitle_mode": "always"}``).
    """
    kwargs: dict[str, Any] = {}
    if "preferred_audio_language" in raw:
        kwargs["preferred_audio_language"] = LanguageCode(raw["preferred_audio_language"])
    if "preferred_subtitle_language" in raw:
        val = raw["preferred_subtitle_language"]
        kwargs["preferred_subtitle_language"] = LanguageCode(val) if val else None
    if "subtitle_mode" in raw:
        kwargs["subtitle_mode"] = SubtitleMode(raw["subtitle_mode"])
    for flag in ("generate_thumbnails", "detect_intros", "auto_refresh_metadata"):
        if flag in raw:
            kwargs[flag] = raw[flag]
    return LibrarySettings(**kwargs)


__all__ = ["CreateLibraryUseCase"]
