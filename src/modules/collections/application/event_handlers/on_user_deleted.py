"""Cross-BC handler: drop watchlist + custom lists when a user is deleted."""

import logging

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.modules.collections.application.unit_of_work import (
    CollectionsUnitOfWorkFactory,
)
from src.shared_kernel.integration_events import UserDeletedEvent

_logger = logging.getLogger(__name__)


class OnUserDeletedHandler(EventHandler):
    """Soft-delete watchlist + custom list rows for the user's profiles.

    Distinct from the promote-to-series handler, which *repoints*
    list refs at a new media id: when the *user* is gone the list
    has no owner, so survival isn't an option — soft-delete keeps
    the rows around for forensic / restore purposes without making
    them visible to anyone else.

    Both writes run inside the same Unit of Work so a partial
    failure (e.g. watchlists wiped but the DB drops before custom
    lists) rolls back, keeping the two tables consistent.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, event: DomainEvent) -> None:
        """Handle ``UserDeletedEvent``."""
        if not isinstance(event, UserDeletedEvent):
            return

        if not event.profile_ids:
            return

        profile_ids = list(event.profile_ids)
        async with self._uow_factory() as uow:
            watchlist_deleted = await uow.watchlist.delete_all_for_profiles(profile_ids)
            lists_deleted = await uow.custom_lists.delete_all_for_profiles(profile_ids)
            # Drop follows the deleted profiles made. Follows *of* their
            # lists don't need explicit cleanup: the lists are now
            # soft-deleted, so ``find_by_id_unscoped`` skips them and no
            # follower gets a dangling read.
            follows_deleted = await uow.list_follows.delete_all_for_followers(profile_ids)

        if watchlist_deleted or lists_deleted or follows_deleted:
            _logger.info(
                "Cleared %d watchlist + %d custom-list + %d follow row(s) for deleted "
                "user %s (%d profile(s))",
                watchlist_deleted,
                lists_deleted,
                follows_deleted,
                event.user_id,
                len(profile_ids),
            )


__all__ = ["OnUserDeletedHandler"]
