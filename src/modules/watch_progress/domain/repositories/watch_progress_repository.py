"""WatchProgress repository interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import WatchableMediaId
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId
from src.shared_kernel.value_objects.profile_id import ProfileId


@dataclass(frozen=True)
class RecentlyWatchedCursor:
    """Keyset position in a profile's recently-watched stream.

    The stream is ordered by ``(last_watched_at DESC, media_id DESC)``.
    ``media_id`` breaks ties and makes the order total, since a profile
    holds at most one row per media (``UNIQUE(profile_id, media_id)``).

    Attributes:
        last_watched_at: ``last_watched_at`` of the last row read.
        media_id: Raw ``media_id`` of the last row read — kept as the
            stored string, because the row it came from may not parse
            as a :class:`WatchableMediaId`.
    """

    last_watched_at: datetime
    media_id: str


@dataclass(frozen=True)
class RecentlyWatchedPage:
    """One page of a profile's recently-watched stream.

    Attributes:
        items: Rows of the page, in stream order, with corrupt rows
            already dropped — so a page can be empty and still not be
            the last one.
        next_cursor: Position of the last *stored* row of the page,
            corrupt or not, to resume after; ``None`` when the stream is
            exhausted.
    """

    items: list[WatchProgress]
    next_cursor: RecentlyWatchedCursor | None


class WatchProgressRepository(ABC):
    """Abstract repository for WatchProgress persistence.

    Every read/delete method takes ``profile_id`` so rows from one
    profile never leak into another's view (e.g. Continue Watching
    only shows the caller's own progress). ``save`` reads the
    ``profile_id`` directly from the entity.

    Example:
        >>> progress = await repo.find_by_media_id(
        ...     WatchableMediaId("mov_abc123def456"), caller_profile_id
        ... )
    """

    @abstractmethod
    async def find_by_media_id(
        self,
        media_id: WatchableMediaId,
        profile_id: ProfileId,
    ) -> WatchProgress | None:
        """Find progress by media + profile.

        Args:
            media_id: Typed watchable id (``mov_xxx`` or composite
                ``epi_ser_xxx_S_E``).
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
    async def list_recently_watched_page(
        self,
        profile_id: ProfileId,
        *,
        limit: int,
        after: RecentlyWatchedCursor | None,
    ) -> RecentlyWatchedPage:
        """Read one keyset page of in-progress + completed items, recent first.

        Covers the same rows as :meth:`list_recently_watched`, in a total
        order, so a caller that discards rows can keep reading without
        skipping or repeating any.

        Args:
            profile_id: The caller's profile.
            limit: Maximum number of stored rows to read for the page.
            after: Resume strictly after this position; ``None`` starts
                from the most recent row.

        Returns:
            The page. Its ``next_cursor`` comes from the last stored row
            read, before corrupt rows are dropped, and is ``None`` when
            fewer than ``limit`` rows were read.
        """

    @abstractmethod
    async def find_by_media_ids(
        self,
        media_ids: list[WatchableMediaId],
        profile_id: ProfileId,
    ) -> dict[str, WatchProgress]:
        """Find progress for multiple media items in a single query.

        Args:
            media_ids: Typed watchable ids to look up.
            profile_id: The caller's profile — only their rows match.

        Returns:
            Dict mapping raw ``media_id`` strings to ``WatchProgress`` for found
            rows. Missing keys mean no progress exists for that
            media in this profile.
        """

    @abstractmethod
    async def delete(self, media_id: WatchableMediaId, profile_id: ProfileId) -> bool:
        """Soft-delete progress for a media item in this profile.

        Args:
            media_id: Typed watchable id of the media.
            profile_id: The caller's profile.

        Returns:
            True if a row was deleted, False if not found.
        """

    @abstractmethod
    async def delete_by_series(
        self,
        series_id: SeriesId,
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
    async def delete_all_for_profiles(self, profile_ids: list[str]) -> int:
        """Soft-delete every progress row owned by the given profiles.

        Cross-BC operation driven by ``UserDeletedEvent``: when an
        admin removes a user every profile they owned is also gone,
        so the half-watched positions belong to nobody. Restoring
        them on a future re-create would be a privacy footgun.

        Not profile-scoped at the caller layer: the handler passes
        in a list of ids in one batch so the cascade is a single
        SQL round-trip instead of one query per profile.

        Args:
            profile_ids: External profile ids (``pro_xxx`` format)
                whose progress rows should be discarded. Empty
                list is a no-op.

        Returns:
            Number of rows soft-deleted across all listed profiles.
        """

    @abstractmethod
    async def delete_all_for_movie(self, movie_id: MovieId) -> int:
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


__all__ = ["RecentlyWatchedCursor", "RecentlyWatchedPage", "WatchProgressRepository"]
