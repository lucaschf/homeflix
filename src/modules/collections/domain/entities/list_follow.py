"""ListFollow aggregate root."""

from __future__ import annotations

from pydantic import Field

from src.building_blocks.domain import AggregateRoot
from src.modules.collections.domain.value_objects import ListFollowId, ListId
from src.shared_kernel.value_objects.profile_id import ProfileId  # noqa: TCH001


class ListFollow(AggregateRoot[ListFollowId]):
    """One profile's live subscription to another profile's shared list.

    A follow is a small, standalone aggregate — one row per
    ``(follower_profile_id, list_id)`` — mirroring the catalog-request
    subscriber pattern (ADR-022). It never copies the owner's items:
    reads always resolve the owner's *current* list, so a followed
    view stays live. The follow only records *who* is watching *which*
    list; every read of that list is re-filtered through the
    follower's own library access (ADR-010), so following can never
    become an access-control bypass.

    The follow timestamp is the inherited ``created_at`` (from
    ``DomainEntity``) — no dedicated ``followed_at`` field, matching
    how ``CatalogSubscription`` leans on the base timestamps.

    Attributes:
        id: External ID (``lfw_xxx`` format).
        follower_profile_id: The profile that follows the list
            (``prf_xxx``). Never the owner — the use case rejects an
            owner following their own list.
        list_id: The shared ``CustomList`` being followed (``lst_xxx``).

    Example:
        >>> follow = ListFollow.create(
        ...     follower_profile_id=ProfileId("prf_3yL8nQsT9mK5"),
        ...     list_id=ListId("lst_abc123def456"),
        ... )
    """

    id: ListFollowId | None = Field(default=None)

    follower_profile_id: ProfileId
    list_id: ListId

    @classmethod
    def create(
        cls,
        follower_profile_id: ProfileId,
        list_id: ListId,
    ) -> ListFollow:
        """Factory method with automatic ID generation.

        Args:
            follower_profile_id: The following profile (``prf_xxx``).
            list_id: The shared list being followed (``lst_xxx``).

        Returns:
            A new ``ListFollow`` instance.
        """
        return cls(
            id=ListFollowId.generate(),
            follower_profile_id=follower_profile_id,
            list_id=list_id,
        )


__all__ = ["ListFollow"]
