"""CustomList aggregate root and CustomListItem entity."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self

from pydantic import Field, field_validator, model_validator

from src.building_blocks.domain import (
    AggregateRoot,
    BusinessRuleViolationException,
    DomainEntity,
)
from src.modules.collections.domain.value_objects import (
    CollectionMediaId,  # — runtime for Pydantic
    CustomListItemId,
    ListId,
    ListName,
    ShareToken,  # — runtime for Pydantic
)
from src.shared_kernel.value_objects import (
    MediaType,  # — runtime for Pydantic
)
from src.shared_kernel.value_objects.profile_id import ProfileId  # noqa: TCH001

MAX_LISTS = 10
MAX_ITEMS_PER_LIST = 100


class CustomListItem(DomainEntity[CustomListItemId]):
    """An item within a custom list.

    Represents a movie or series added to a user-created list.

    Attributes:
        id: External ID (cli_xxx format).
        media_id: Typed catalog id (``mov_xxx`` or ``ser_xxx``); must
            match ``media_type``.
        media_type: Type of media (movie or series).
        position: Ordering position within the list.
        added_at: Timestamp when the item was added.

    Example:
        >>> item = CustomListItem.create(
        ...     media_id=CollectionMediaId("mov_abc123def456"),
        ...     media_type=MediaType.MOVIE,
        ...     position=0,
        ... )
    """

    id: CustomListItemId | None = Field(default=None)

    media_id: CollectionMediaId
    media_type: MediaType
    position: int = 0
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _validate_media_id_matches_type(self) -> Self:
        """Reject a movie id paired with series type and vice versa."""
        if self.media_id.is_movie != (self.media_type is MediaType.MOVIE):
            raise ValueError(
                f"media_id '{self.media_id.value}' does not match "
                f"media_type '{self.media_type.value}'",
            )
        return self

    @classmethod
    def create(
        cls,
        media_id: CollectionMediaId,
        media_type: MediaType,
        position: int = 0,
    ) -> CustomListItem:
        """Factory method with automatic ID generation.

        Args:
            media_id: Typed catalog id (``mov_xxx`` or ``ser_xxx``).
            media_type: Type of media (movie or series).
            position: Ordering position within the list.

        Returns:
            A new CustomListItem instance.
        """
        return cls(
            id=CustomListItemId.generate(),
            media_id=media_id,
            media_type=media_type,
            position=position,
            added_at=datetime.now(UTC),
        )


class CustomList(AggregateRoot[ListId]):
    """A user-created custom list of media items.

    Represents a named collection like Crunchyroll's "Crunchylistas".
    Users can create up to MAX_LISTS lists, each holding up to
    MAX_ITEMS_PER_LIST items.

    Attributes:
        id: External ID (lst_xxx format).
        name: Display name of the list.
        item_count: Number of items currently in the list.

    Example:
        >>> custom_list = CustomList.create(
        ...     profile_id=profile_id, name="Action Movies", existing_count=0
        ... )
    """

    id: ListId | None = Field(default=None)

    profile_id: ProfileId
    name: ListName
    description: str | None = Field(default=None, max_length=500)
    item_count: int = 0
    # Presence of a token ⇒ the list is shared. Cleared on revoke.
    share_token: ShareToken | None = Field(default=None)

    @property
    def is_shared(self) -> bool:
        """Whether the list currently carries a live share token."""
        return self.share_token is not None

    @field_validator("name", mode="before")
    @classmethod
    def convert_name(cls, v: str | ListName) -> ListName:
        """Convert string to ListName if needed."""
        return ListName(v) if isinstance(v, str) else v

    @classmethod
    def create(
        cls,
        profile_id: ProfileId,
        name: str | ListName,
        *,
        existing_count: int,
        description: str | None = None,
    ) -> CustomList:
        """Factory method with automatic ID generation.

        Enforces the per-profile list limit (ADR-017): the caller fetches
        how many lists the profile already has and the factory decides.
        The keyword-only argument makes the check impossible to bypass
        by omission.

        Args:
            profile_id: Owning profile (``prf_xxx``). Every list is scoped
                to a single profile so multi-profile households keep
                their lists separate.
            name: Display name for the list.
            existing_count: Number of lists the profile already has.
            description: Optional free-text description.

        Returns:
            A new CustomList instance.

        Raises:
            BusinessRuleViolationException: When the profile already has
                ``MAX_LISTS`` lists.
        """
        if existing_count >= MAX_LISTS:
            raise BusinessRuleViolationException(
                message=f"Cannot create more than {MAX_LISTS} custom lists",
                message_code="CUSTOM_LIST_LIMIT_EXCEEDED",
                rule_code="CUSTOM_LIST_LIMIT_EXCEEDED",
            )
        return cls(
            id=ListId.generate(),
            profile_id=profile_id,
            name=name,
            description=description,
            item_count=0,
        )

    def rename(self, new_name: str | ListName) -> CustomList:
        """Create a copy with the new name.

        Args:
            new_name: The new display name.

        Returns:
            A new CustomList instance with updated name.
        """
        return self.with_updates(name=new_name)

    def with_details(self, *, name: str | ListName, description: str | None) -> CustomList:
        """Create a copy with the edited name and description.

        Both are authoritative — the edit form sends the full state, so
        passing ``description=None`` clears it.

        Args:
            name: The new display name.
            description: The new description, or ``None`` to clear it.

        Returns:
            A new CustomList instance with both fields updated.
        """
        return self.with_updates(name=name, description=description)

    def shared(self) -> CustomList:
        """Return a shared copy, minting a token if absent (idempotent).

        Sharing twice is a no-op: an already-shared list keeps its
        existing token so the link a member already copied stays valid.

        Returns:
            ``self`` when already shared, otherwise a copy carrying a
            freshly minted :class:`ShareToken`.
        """
        if self.share_token is not None:
            return self
        return self.with_updates(share_token=ShareToken.generate())

    def unshared(self) -> CustomList:
        """Return an unshared copy, clearing any token (idempotent).

        Revoking a list that was never shared is a no-op.

        Returns:
            ``self`` when not shared, otherwise a copy with the token
            cleared so the old link stops resolving.
        """
        if self.share_token is None:
            return self
        return self.with_updates(share_token=None)

    def increment_item_count(self) -> CustomList:
        """Increment item count after adding an item.

        Returns:
            A new CustomList instance with incremented count.

        Raises:
            BusinessRuleViolationException: If the list is already full.
        """
        if self.item_count >= MAX_ITEMS_PER_LIST:
            raise BusinessRuleViolationException(
                message=f"Custom list cannot have more than {MAX_ITEMS_PER_LIST} items",
                message_code="CUSTOM_LIST_ITEM_LIMIT_EXCEEDED",
                rule_code="CUSTOM_LIST_ITEM_LIMIT_EXCEEDED",
            )
        return self.with_updates(item_count=self.item_count + 1)

    def decrement_item_count(self) -> CustomList:
        """Decrement item count after removing an item.

        Returns:
            A new CustomList instance with decremented count.
        """
        return self.with_updates(item_count=max(0, self.item_count - 1))


__all__ = ["CustomList", "CustomListItem", "MAX_ITEMS_PER_LIST", "MAX_LISTS"]
