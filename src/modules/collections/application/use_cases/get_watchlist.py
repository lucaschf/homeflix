"""GetWatchlistUseCase - List watchlist items with media metadata."""

import logging
from typing import TYPE_CHECKING

from src.modules.collections.application.dtos import (
    GetWatchlistInput,
    WatchlistItemOutput,
)
from src.modules.collections.application.ports import (
    MediaLookupPort,
    MediaSummary,
    ProfileViewingPolicyPort,
    ProgressLookupPort,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.application.use_cases._item_projection import permits_summary
from src.modules.collections.domain.entities import WatchlistItem
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from src.modules.collections.domain.repositories import WatchlistCursor

_logger = logging.getLogger(__name__)

#: Minimum stored rows read per keyset page while filling the list. A small
#: ``limit`` must not turn every hidden row into its own round trip, and the
#: front end's default ``limit`` of 100 stays a single page.
_PAGE_ROWS = 100


class GetWatchlistUseCase:
    """List the caller's watchlist items with display metadata.

    Joins watchlist records with the Media BC's display data (title,
    poster) via ``MediaLookupPort`` so this use case never talks to
    media repositories directly. Uses one batch lookup per page to avoid
    N+1 queries.

    Only titles the caller's profile can see are listed. ``limit`` counts
    listed items: an item whose media is missing, outside the caller's
    libraries or above the caller's maturity limit is skipped without
    using up the limit, so the three cases produce the same list and a
    small ``limit`` cannot be used to tell them apart. The list is filled
    by keyset pages over the profile's own watchlist, never by offset.

    Example:
        >>> use_case = GetWatchlistUseCase(
        ...     uow_factory, media_lookup, progress_lookup, profile_viewing_policy
        ... )
        >>> items = await use_case.execute(GetWatchlistInput(limit=50, lang="pt-BR"))
    """

    def __init__(
        self,
        uow_factory: CollectionsUnitOfWorkFactory,
        media_lookup: MediaLookupPort,
        progress_lookup: ProgressLookupPort,
        profile_viewing_policy: ProfileViewingPolicyPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
            media_lookup: Port for resolving media display metadata.
            progress_lookup: Port for resolving the caller's watch progress.
            profile_viewing_policy: Port for the caller's viewing policy.
        """
        self._uow_factory = uow_factory
        self._media_lookup = media_lookup
        self._progress_lookup = progress_lookup
        self._profile_viewing_policy = profile_viewing_policy

    async def execute(self, input_dto: GetWatchlistInput) -> list[WatchlistItemOutput]:
        """Execute the use case.

        Args:
            input_dto: Contains limit and language.

        Returns:
            List of WatchlistItemOutput with media metadata.
        """
        profile_id = ProfileId(input_dto.profile_id)
        policy = await self._profile_viewing_policy.find_for_profile(profile_id)
        if policy.denies_everything:
            return []

        visible = await self._visible_items(profile_id, input_dto.limit, input_dto.lang, policy)
        _logger.info("Found %d watchlist items", len(visible))

        if not visible:
            return []

        # Progress only exists for movies (series progress lives on
        # episodes — deferred), so look up movie ids only.
        movie_id_strs = [
            item.media_id.value for item, _ in visible if item.media_type == MediaType.MOVIE
        ]
        progress = await self._progress_lookup.get_progress(
            movie_id_strs, profile_id=input_dto.profile_id
        )

        return [
            WatchlistItemOutput.from_entity(
                entity=item,
                summary=summary,
                progress=progress.get(item.media_id.value),
            )
            for item, summary in visible
        ]

    async def _visible_items(
        self,
        profile_id: ProfileId,
        limit: int,
        lang: str,
        policy: ViewingPolicy,
    ) -> list[tuple[WatchlistItem, MediaSummary]]:
        """Collect the ``limit`` most recently added items the policy lets through.

        Reads the watchlist in keyset pages of ``limit`` rows, but never
        fewer than ``_PAGE_ROWS``, each in its own short collections
        transaction, and resolves each page's media in one batch. Rows are
        taken in watchlist order; a row is skipped without counting when
        its ``media_id`` was already read, its media is missing (logged, as
        before) or the policy denies it (silently — a restricted title is
        not an anomaly).

        Reading stops, with a warning, when a page's cursor did not advance
        past the one it was read after: the same rows would be read again
        forever.

        Args:
            profile_id: The caller's profile.
            limit: Number of items to collect.
            lang: Language for localized titles/genres.
            policy: The caller's viewing policy.

        Returns:
            Up to ``limit`` items with their media summaries, most
            recently added first.
        """
        visible: list[tuple[WatchlistItem, MediaSummary]] = []
        seen: set[str] = set()
        cursor: WatchlistCursor | None = None
        page_rows = max(limit, _PAGE_ROWS)

        while len(visible) < limit:
            async with self._uow_factory() as uow:
                page = await uow.watchlist.list_page(profile_id, limit=page_rows, after=cursor)

            fresh = [item for item in page.items if item.media_id.value not in seen]
            seen.update(item.media_id.value for item in fresh)
            summaries = await self._summaries(fresh, lang)

            for item in fresh:
                summary = summaries.get((item.media_type, item.media_id.value))
                if summary is None:
                    _logger.warning("Could not find media for watchlist item: %s", item.media_id)
                    continue
                if not permits_summary(policy, summary):
                    continue
                visible.append((item, summary))
                if len(visible) == limit:
                    break

            if page.next_cursor is None:
                break
            if page.next_cursor == cursor:
                _logger.warning("Watchlist cursor did not advance for profile: %s", profile_id)
                break
            cursor = page.next_cursor

        return visible

    async def _summaries(
        self,
        items: list[WatchlistItem],
        lang: str,
    ) -> dict[tuple[MediaType, str], MediaSummary]:
        """Resolve the media of ``items`` in one batch; no lookup when empty."""
        if not items:
            return {}
        movie_ids = [i.media_id.as_movie_id() for i in items if i.media_type == MediaType.MOVIE]
        series_ids = [i.media_id.as_series_id() for i in items if i.media_type == MediaType.SERIES]
        return await self._media_lookup.get_many(movie_ids, series_ids, lang)


__all__ = ["GetWatchlistUseCase"]
