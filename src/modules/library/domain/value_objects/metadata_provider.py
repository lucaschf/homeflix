"""Metadata provider enumeration and configuration."""

from enum import StrEnum

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class MetadataProvider(StrEnum):
    """Available metadata providers for fetching media information.

    Each provider has different strengths:
    - TMDB: Best for movies, good international coverage
    - OMDB: Good fallback, includes Rotten Tomatoes scores
    - TVDB: Best for TV series, especially anime

    Example:
        >>> provider = MetadataProvider.TMDB
        >>> provider.value
        'tmdb'
    """

    TMDB = "tmdb"
    OMDB = "omdb"
    TVDB = "tvdb"


class MetadataProviderConfig(CompoundValueObject):
    """Configuration for a metadata provider within a library.

    Defines the priority order and enabled state for a provider in
    the metadata fetching chain.

    Attributes:
        provider: The metadata provider to use.
        priority: Order in the fallback chain (1 = first, lower = higher priority).
        enabled: Whether this provider is active.

    Example:
        >>> config = MetadataProviderConfig(
        ...     provider=MetadataProvider.TMDB,
        ...     priority=1,
        ...     enabled=True,
        ... )
        >>> config.provider
        <MetadataProvider.TMDB: 'tmdb'>
    """

    provider: MetadataProvider
    priority: int = Field(ge=1, le=10)
    enabled: bool = True

    @classmethod
    def tmdb(cls, priority: int = 1) -> "MetadataProviderConfig":
        """Factory for TMDB provider config.

        Args:
            priority: Priority in the fallback chain.

        Returns:
            A MetadataProviderConfig for TMDB.
        """
        return cls(provider=MetadataProvider.TMDB, priority=priority)

    @classmethod
    def omdb(cls, priority: int = 2) -> "MetadataProviderConfig":
        """Factory for OMDb provider config.

        Args:
            priority: Priority in the fallback chain.

        Returns:
            A MetadataProviderConfig for OMDb.
        """
        return cls(provider=MetadataProvider.OMDB, priority=priority)

    @classmethod
    def tvdb(cls, priority: int = 1) -> "MetadataProviderConfig":
        """Factory for TVDB provider config.

        Args:
            priority: Priority in the fallback chain.

        Returns:
            A MetadataProviderConfig for TVDB.
        """
        return cls(provider=MetadataProvider.TVDB, priority=priority)


__all__ = ["MetadataProvider", "MetadataProviderConfig"]
