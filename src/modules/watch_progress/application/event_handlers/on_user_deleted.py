"""Cross-BC handler: clear watch progress when a user is deleted."""

import logging

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)
from src.shared_kernel.integration_events import UserDeletedEvent

_logger = logging.getLogger(__name__)


class OnUserDeletedHandler(EventHandler):
    """Soft-delete every ``watch_progresses`` row owned by the user's profiles.

    A user delete is treated as a privacy-driven wipe: the ex-user's
    half-watched positions belong to nobody and shouldn't be visible
    if the row is ever rehydrated. Lists the profile ids explicitly
    in the event (rather than re-querying identity, which would race
    against the soft-delete tombstone) so this handler never needs a
    cross-BC read.

    Runs out of the event bus, which is fire-and-forget — failures
    are logged but the user-delete still commits. The operator can
    re-run the cleanup later if a downstream BC was offline.
    """

    def __init__(self, uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, event: DomainEvent) -> None:
        """Handle ``UserDeletedEvent``."""
        if not isinstance(event, UserDeletedEvent):
            return

        if not event.profile_ids:
            return

        async with self._uow_factory() as uow:
            deleted = await uow.progress.delete_all_for_profiles(
                list(event.profile_ids),
            )

        if deleted:
            _logger.info(
                "Cleared %d watch_progress row(s) for deleted user %s " "(%d profile(s))",
                deleted,
                event.user_id,
                len(event.profile_ids),
            )


__all__ = ["OnUserDeletedHandler"]
