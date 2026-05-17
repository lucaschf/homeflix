"""WatchProgress repository interface."""

from abc import ABC, abstractmethod

from src.modules.watch_progress.domain.entities import WatchProgress
from src.shared_kernel.value_objects.profile_id import ProfileId


class WatchProgressRepository(ABC):
    """Abstract repository for WatchProgress persistence.

    Every read/delete method takes ``profile_id`` so rows from one
    profile never leak into another's view (e.g. Continue Watching
    only shows the caller's own progress). ``save`` reads the
    ``profile_id`` directly from the entity.

    Example:
        >>> progress = await repo.find_by_media_id(
        ...     "mov_abc123def456", caller_profile_id
        ... )
    """

    @abstractmethod
    async def find_by_media_id(
        self,
        media_id: str,
        profile_id: ProfileId,
    ) -> WatchProgress | None:
        """Find progress by media + profile.

        Args:
            media_id: External ID of the media (``mov_xxx`` or
                ``epi_xxx``).
            profile_id: The caller's profile.

        Returns:
            WatchProgress if a row exists for this profile/media,
            ``None`` otherwise.
        """

    @abstractmethod
    async def save(self, progress: WatchProgress) -> WatchProgress:
        """Create or update a watch progress record.

        Profile scoping comes from ``progress.profile_id`` — the
        caller does not pass it separately.

        Args:
            progress: The WatchProgress entity to persist.

        Returns:
            The persisted WatchProgress.
        """

    @abstractmethod
    async def list_in_progress(
        self,
        profile_id: ProfileId,
        limit: int = 20,
    ) -> list[WatchProgress]:
        """List in-progress items for the profile, most recent first."""

    @abstractmethod
    async def list_recently_watched(
        self,
        profile_id: ProfileId,
        limit: int = 20,
    ) -> list[WatchProgress]:
        """List in-progress + completed items for the profile, recent first."""

    @abstractmethod
    async def find_by_media_ids(
        self,
        media_ids: list[str],
        profile_id: ProfileId,
    ) -> dict[str, WatchProgress]:
        """Find progress for multiple media items in a single query.

        Args:
            media_ids: List of external media IDs to look up.
            profile_id: The caller's profile — only their rows match.

        Returns:
            Dict mapping ``media_id`` to ``WatchProgress`` for found
            rows. Missing keys mean no progress exists for that
            media in this profile.
        """

    @abstractmethod
    async def delete(self, media_id: str, profile_id: ProfileId) -> bool:
        """Soft-delete progress for a media item in this profile.

        Args:
            media_id: External ID of the media.
            profile_id: The caller's profile.

        Returns:
            True if a row was deleted, False if not found.
        """

    @abstractmethod
    async def delete_by_series(
        self,
        series_id: str,
        profile_id: ProfileId,
    ) -> int:
        """Soft-delete every episode progress for a series in this profile.

        Matches every row whose ``media_id`` starts with
        ``epi_{series_id}_`` (the composite-id format produced by
        ``EpisodeCompositeId.build()``) and belongs to ``profile_id``.

        Args:
            series_id: External series ID (``ser_xxx`` format).
            profile_id: The caller's profile.

        Returns:
            Number of rows soft-deleted.
        """

    @abstractmethod
    async def delete_all_for_movie(self, movie_id: str) -> int:
        """Soft-delete every progress row that points at a movie id.

        Cross-BC operation driven by ``MoviePromotedToSeriesEvent``:
        when a movie is converted to a series the old ``mov_xxx``
        identity disappears, and re-anchoring a half-watched
        playback position to a re-cut episode would almost always
        land the user mid-scene. Wiping the progress is the safest
        option — the operator can scrub manually next time.

        Unlike ``delete()`` this is *not* profile-scoped: every
        affected profile's row is removed in one call so the cross-BC
        handler doesn't need to fan out per profile.

        Args:
            movie_id: External movie id (``mov_xxx`` format).

        Returns:
            Number of rows soft-deleted (may be 0 if no one had
            progress on that movie yet).
        """


__all__ = ["WatchProgressRepository"]
