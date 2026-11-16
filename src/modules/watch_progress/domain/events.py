"""Domain events for the Watch Progress bounded context."""

from dataclasses import dataclass

from src.building_blocks.domain.events import DomainEvent
from src.modules.watch_progress.domain.value_objects import WatchableMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


@dataclass(frozen=True, kw_only=True)
class WatchCompletedEvent(DomainEvent):
    """Emitted when a profile's progress on a title reaches completion.

    Raised once, on the transition into ``COMPLETED``: rewatching a title
    that is already completed raises nothing.

    Attributes:
        profile_id: Profile that finished the title.
        media_id: The movie or episode that was finished.
    """

    profile_id: ProfileId
    media_id: WatchableMediaId


__all__ = ["WatchCompletedEvent"]
