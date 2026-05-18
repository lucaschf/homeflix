"""Domain events for the Identity bounded context."""

from dataclasses import dataclass, field

from src.building_blocks.domain.events import DomainEvent


@dataclass(frozen=True)
class UserDeletedEvent(DomainEvent):
    """Emitted when an admin soft-deletes a user account.

    Carries the full list of profile ids owned by the deleted user
    so downstream bounded contexts can cascade their per-profile
    state without re-querying identity (which would race against the
    soft-delete tombstone). Profile ids are passed by-value because
    cross-BC FKs are forbidden by ADR-008.

    Cross-BC handlers:
        - ``watch_progress`` soft-deletes every ``watch_progresses``
          row whose ``profile_id`` matches one of the deleted user's
          profiles. The half-watched position belongs to that
          person; restoring it later would be a privacy footgun.
        - ``collections`` soft-deletes the user's watchlists and
          custom lists (lists belong to profiles, not users) so the
          ex-user's library state isn't visible to anyone else.

    Both handlers run fire-and-forget on the event bus — failures
    are logged but the user-delete still commits. Operators can
    re-run the cleanup later if a downstream BC was offline.

    Attributes:
        user_id: External ID of the deleted user (usr_xxx).
        profile_ids: External IDs of every profile the user owned
            at deletion time (pro_xxx). May be empty if the user
            never created a profile.
    """

    user_id: str = ""
    profile_ids: tuple[str, ...] = field(default_factory=tuple)


__all__ = ["UserDeletedEvent"]
