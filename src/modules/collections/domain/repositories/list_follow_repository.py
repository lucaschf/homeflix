"""ListFollow repository interface."""

from abc import ABC, abstractmethod

from src.modules.collections.domain.entities import ListFollow
from src.modules.collections.domain.value_objects import ListId
from src.shared_kernel.value_objects.profile_id import ProfileId


class ListFollowRepository(ABC):
    """Abstract repository for ``ListFollow`` persistence.

    Follows are the live link between a follower profile and a shared
    list. The natural key ``(follower_profile_id, list_id)`` is unique
    among live rows so a repeat follow stays idempotent.

    Example:
        >>> follow = await repo.find(follower_id, list_id)
        >>> follows = await repo.list_for_follower(follower_id)
    """

    @abstractmethod
    async def add(self, follow: ListFollow) -> ListFollow:
        """Persist a new follow."""

    @abstractmethod
    async def find(
        self,
        follower_profile_id: ProfileId,
        list_id: ListId,
    ) -> ListFollow | None:
        """Look up a single live follow by its natural key."""

    @abstractmethod
    async def remove(
        self,
        follower_profile_id: ProfileId,
        list_id: ListId,
    ) -> bool:
        """Soft-delete a follow by its natural key (unfollow).

        Returns ``True`` when a live row was removed, ``False`` when
        there was nothing to remove (idempotent unfollow).
        """

    @abstractmethod
    async def list_for_follower(self, follower_profile_id: ProfileId) -> list[ListFollow]:
        """List every live follow owned by ``follower_profile_id``."""

    @abstractmethod
    async def remove_all_for_list(self, list_id: ListId) -> int:
        """Soft-delete every follow of a single list.

        Driven by the owner deleting or revoking the list: existing
        followers must lose the follow so the list disappears from
        their surface with no dangling read.

        Returns:
            Number of live follows removed.
        """

    @abstractmethod
    async def delete_all_for_followers(self, follower_profile_ids: list[str]) -> int:
        """Soft-delete every follow *made by* the given profiles.

        Cross-BC cleanup driven by ``UserDeletedEvent`` — when a user
        (and their profiles) is gone, the follows they made must go
        too. Empty list is a no-op.

        Returns:
            Number of live follows removed.
        """


__all__ = ["ListFollowRepository"]
