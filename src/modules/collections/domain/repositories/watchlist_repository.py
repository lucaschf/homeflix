"""Watchlist repository interface."""

from abc import ABC, abstractmethod

from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects import CollectionMediaType
from src.shared_kernel.value_objects.profile_id import ProfileId


class WatchlistRepository(ABC):
    """Abstract repository for ``WatchlistItem`` persistence.

    Every read/delete operation takes ``profile_id`` so a profile only
    sees its own watchlist. ``add`` reads the profile from the entity.

    Example:
        >>> item = await repo.find_by_media_id(
        ...     CollectionMediaId("mov_abc123def456"), caller_profile_id
        ... )
    """

    @abstractmethod
    async def find_by_media_id(
        self,
        media_id: CollectionMediaId,
        profile_id: ProfileId,
    ) -> WatchlistItem | None:
        """Find an entry for ``media_id`` in ``profile_id``'s watchlist."""

    @abstractmethod
    async def add(self, item: WatchlistItem) -> WatchlistItem:
        """Add an item (profile is read from the entity)."""

    @abstractmethod
    async def remove(self, media_id: CollectionMediaId, profile_id: ProfileId) -> bool:
        """Soft-delete an item from ``profile_id``'s watchlist."""

    @abstractmethod
    async def list_all(
        self,
        profile_id: ProfileId,
        limit: int = 100,
    ) -> list[WatchlistItem]:
        """List the profile's watchlist items, most recently added first."""

    @abstractmethod
    async def exists(self, media_id: CollectionMediaId, profile_id: ProfileId) -> bool:
        """Check whether ``media_id`` is on ``profile_id``'s watchlist."""

    @abstractmethod
    async def delete_all_for_profiles(self, profile_ids: list[str]) -> int:
        """Soft-delete every watchlist row owned by the given profiles.

        Cross-BC operation driven by ``UserDeletedEvent``: when an
        admin removes a user, the profiles they owned vanish too,
        so the watchlists belong to nobody.

        Args:
            profile_ids: External profile ids (``pro_xxx`` format)
                whose watchlist rows should be discarded. Empty
                list is a no-op.

        Returns:
            Number of rows soft-deleted across all listed profiles.
        """

    @abstractmethod
    async def rewrite_media_id(
        self,
        from_media_id: CollectionMediaId,
        to_media_id: CollectionMediaId,
        to_media_type: CollectionMediaType,
    ) -> int:
        """Repoint every row from one media id to another (cross-profile).

        Driven by ``MoviePromotedToSeriesEvent``: when a movie is
        converted to a series, every profile's watchlist entry for
        the old ``mov_xxx`` id needs to land on the new ``ser_xxx``
        id so the list keeps the same set of titles without manual
        cleanup. ``media_type`` is rewritten too because watchlist
        rows carry the discriminator alongside the id.

        Args:
            from_media_id: External id currently stored.
            to_media_id: External id to migrate to.
            to_media_type: New ``media_type`` discriminator
                (``"series"`` for the promote flow).

        Returns:
            Number of rows updated.
        """


__all__ = ["WatchlistRepository"]
