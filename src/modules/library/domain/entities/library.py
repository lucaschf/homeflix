"""Library aggregate root."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from pydantic import Field, field_validator, model_validator

if TYPE_CHECKING:
    from collections.abc import Sequence

from src.building_blocks.domain.entity import AggregateRoot
from src.modules.library.domain.rule_codes import LibraryRuleCodes
from src.modules.library.domain.value_objects.library_id import LibraryId
from src.modules.library.domain.value_objects.library_name import LibraryName
from src.modules.library.domain.value_objects.library_settings import LibrarySettings
from src.modules.library.domain.value_objects.library_type import LibraryType
from src.modules.library.domain.value_objects.metadata_provider import MetadataProviderConfig
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.language_code import LanguageCode


class Library(AggregateRoot[LibraryId]):
    """A configured media library with scan and playback settings.

    Represents a collection of media from one or more filesystem paths,
    with specific metadata providers and user preferences.

    Attributes:
        id: External ID (lib_xxx format).
        name: User-friendly display name.
        library_type: Type of content (movies, series, mixed).
        paths: Filesystem paths to scan for media.
        language: Preferred language for metadata fetching (ISO 639-1).
        metadata_providers: Ordered list of metadata sources with fallback.
        scan_schedule: Cron expression for automatic scanning, or None.
        settings: Additional library-specific settings.

    Example:
        >>> library = Library.create(
        ...     name="Anime",
        ...     library_type=LibraryType.SERIES,
        ...     paths=["/media/anime"],
        ...     language="ja",
        ... )
        >>> library.name.value
        'Anime'
    """

    # Identity
    id: LibraryId | None = Field(default=None)

    # Core info
    name: LibraryName
    library_type: LibraryType
    paths: list[FilePath] = Field(min_length=1)
    language: LanguageCode = Field(default_factory=LanguageCode.english)

    # Metadata configuration
    metadata_providers: list[MetadataProviderConfig] = Field(default_factory=list)

    # Scan configuration
    scan_schedule: str | None = Field(
        default=None,
        pattern=r"^(\S+\s+){4}\S+$",
    )

    # Settings
    settings: LibrarySettings = Field(default_factory=LibrarySettings.default)

    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | LibraryId | None) -> LibraryId | None:
        """Convert string to LibraryId if needed."""
        if v is None:
            return None
        return LibraryId(v) if isinstance(v, str) else v

    @field_validator("name", mode="before")
    @classmethod
    def convert_name(cls, v: str | LibraryName) -> LibraryName:
        """Convert string to LibraryName if needed."""
        return LibraryName(v) if isinstance(v, str) else v

    @field_validator("paths", mode="before")
    @classmethod
    def convert_paths(cls, v: Any) -> list[FilePath]:
        """Normalize and convert input to a list of FilePath."""
        if v is None:
            return []
        if isinstance(v, str | FilePath):
            v = [v]
        return [FilePath(p) if isinstance(p, str) else p for p in v]

    @field_validator("language", mode="before")
    @classmethod
    def convert_language(cls, v: str | LanguageCode) -> LanguageCode:
        """Convert string to LanguageCode if needed."""
        return LanguageCode(v) if isinstance(v, str) else v

    @model_validator(mode="after")
    def validate_library(self) -> Library:
        """Validate library configuration.

        Returns:
            The validated library.

        Raises:
            ValueError: If paths are empty or have duplicates.
        """
        if not self.paths:
            raise ValueError(
                f"Library must have at least one path [{LibraryRuleCodes.LIBRARY_NO_PATHS}]"
            )

        # Check for duplicate paths
        path_values = [p.value for p in self.paths]
        if len(path_values) != len(set(path_values)):
            raise ValueError(
                f"Library paths must be unique [{LibraryRuleCodes.LIBRARY_DUPLICATE_PATH}]"
            )

        # Validate metadata provider priorities are unique
        if self.metadata_providers:
            priorities = [p.priority for p in self.metadata_providers if p.enabled]
            if len(priorities) != len(set(priorities)):
                raise ValueError(
                    f"Enabled metadata providers must have unique priorities "
                    f"[{LibraryRuleCodes.DUPLICATE_PROVIDER_PRIORITY}]"
                )

        return self

    def with_path(self, path: FilePath | str) -> Self:
        """Return a copy with the path added.

        Args:
            path: Filesystem path to add.

        Returns:
            A new Library with the path added.

        Raises:
            ValueError: If path already exists in the library.
        """
        if isinstance(path, str):
            path = FilePath(path)

        if path in self.paths:
            raise ValueError(
                f"Path already exists in library [{LibraryRuleCodes.LIBRARY_DUPLICATE_PATH}]"
            )

        return self.with_updates(paths=[*self.paths, path])

    def without_path(self, path: FilePath | str) -> Self:
        """Return a copy with the path removed.

        Args:
            path: Filesystem path to remove.

        Returns:
            A new Library without the path, or self if not found.

        Raises:
            ValueError: If removing the last path.
        """
        if isinstance(path, str):
            path = FilePath(path)

        if path not in self.paths:
            return self

        if len(self.paths) == 1:
            raise ValueError(
                f"Cannot remove the last path from library "
                f"[{LibraryRuleCodes.LIBRARY_NO_PATHS}]"
            )

        return self.with_updates(paths=[p for p in self.paths if p != path])

    def get_enabled_providers(self) -> list[MetadataProviderConfig]:
        """Get enabled metadata providers sorted by priority.

        Returns:
            List of enabled providers, sorted by priority (lowest first).
        """
        enabled = [p for p in self.metadata_providers if p.enabled]
        return sorted(enabled, key=lambda p: p.priority)

    @classmethod
    def create(
        cls,
        name: str | LibraryName,
        library_type: LibraryType | str,
        paths: Sequence[str | FilePath],
        language: str | LanguageCode = "en",
        metadata_providers: list[MetadataProviderConfig] | None = None,
        settings: LibrarySettings | None = None,
        **kwargs: Any,
    ) -> Library:
        """Factory method with automatic ID generation.

        Args:
            name: Library display name.
            library_type: Type of content in the library.
            paths: Filesystem paths to scan.
            language: Preferred metadata language.
            metadata_providers: Ordered list of metadata sources.
            settings: Library behavior settings.
            **kwargs: Additional optional fields.

        Returns:
            A new Library instance with generated ID.
        """
        library_id = LibraryId.generate()

        if isinstance(name, str):
            name = LibraryName(name)
        if isinstance(library_type, str):
            library_type = LibraryType(library_type)
        if isinstance(language, str):
            language = LanguageCode(language)

        converted_paths = [FilePath(p) if isinstance(p, str) else p for p in paths]

        return cls(
            id=library_id,
            name=name,
            library_type=library_type,
            paths=converted_paths,
            language=language,
            metadata_providers=metadata_providers or [],
            settings=settings or LibrarySettings.default(),
            **kwargs,
        )

    @classmethod
    def create_movie_library(
        cls,
        name: str,
        paths: Sequence[str],
        language: str = "en",
    ) -> Library:
        """Create a library optimized for movies.

        Args:
            name: Library display name.
            paths: Filesystem paths to scan.
            language: Preferred metadata language.

        Returns:
            A new movie Library with TMDB as primary provider.
        """
        return cls.create(
            name=name,
            library_type=LibraryType.MOVIES,
            paths=paths,
            language=language,
            metadata_providers=[
                MetadataProviderConfig.tmdb(priority=1),
                MetadataProviderConfig.omdb(priority=2),
            ],
        )

    @classmethod
    def create_series_library(
        cls,
        name: str,
        paths: Sequence[str],
        language: str = "en",
    ) -> Library:
        """Create a library optimized for TV series.

        Args:
            name: Library display name.
            paths: Filesystem paths to scan.
            language: Preferred metadata language.

        Returns:
            A new series Library with TVDB as primary provider.
        """
        return cls.create(
            name=name,
            library_type=LibraryType.SERIES,
            paths=paths,
            language=language,
            metadata_providers=[
                MetadataProviderConfig.tvdb(priority=1),
                MetadataProviderConfig.tmdb(priority=2),
            ],
        )

    @classmethod
    def create_anime_library(
        cls,
        name: str,
        paths: Sequence[str],
    ) -> Library:
        """Create a library optimized for anime.

        Args:
            name: Library display name.
            paths: Filesystem paths to scan.

        Returns:
            A new anime Library with Japanese metadata and English subtitles.
        """
        return cls.create(
            name=name,
            library_type=LibraryType.SERIES,
            paths=paths,
            language="ja",
            metadata_providers=[
                MetadataProviderConfig.tvdb(priority=1),
                MetadataProviderConfig.tmdb(priority=2),
            ],
            settings=LibrarySettings.for_anime(),
        )


__all__ = ["Library"]
