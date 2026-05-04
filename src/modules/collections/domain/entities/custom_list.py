"""CustomList aggregate root and CustomListItem entity."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field, field_validator

from src.building_blocks.domain import (
    AggregateRoot,
    BusinessRuleViolationException,
    DomainEntity,
)
from src.modules.collections.domain.value_objects import (
    CustomListItemId,
    ListId,
    ListName,
)
from src.shared_kernel.value_objects import (
    CollectionMediaType,  # noqa: TCH001 — runtime for Pydantic
)
from src.shared_kernel.value_objects.profile_id import ProfileId  # noqa: TCH001

MAX_LISTS = 10
MAX_ITEMS_PER_LIST = 100


class CustomListItem(DomainEntity[CustomListItemId]):
    """An item within a custom list.

    Represents a movie or series added to a user-created list.

    Attributes:
        id: External ID (cli_xxx format).
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media (movie or series).
        position: Ordering position within the list.
        added_at: Timestamp when the item was added.

    Example:
        >>> item = CustomListItem.create(
        ...     media_id="mov_abc123def456",
        ...     media_type=CollectionMediaType.MOVIE,
        ...     position=0,
        ... )
    """

    id: CustomListItemId | None = Field(default=None)

    media_id: str
    media_type: CollectionMediaType
    position: int = 0
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        media_id: str,
        media_type: CollectionMediaType,
        position: int = 0,
    ) -> CustomListItem:
        """Factory method with automatic ID generation.

        Args:
            media_id: External ID of the media (mov_xxx or ser_xxx).
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
        >>> custom_list = CustomList.create(name="Action Movies")
    """

    id: ListId | None = Field(default=None)

    profile_id: ProfileId
    name: ListName
    item_count: int = 0

    @field_validator("name", mode="before")
    @classmethod
    def convert_name(cls, v: str | ListName) -> ListName:
        """Convert string to ListName if needed."""
        return ListName(v) if isinstance(v, str) else v

    @classmethod
    def create(cls, profile_id: ProfileId, name: str | ListName) -> CustomList:
        """Factory method with automatic ID generation.

        Args:
            profile_id: Owning profile (``prf_xxx``). Every list is scoped
                to a single profile so multi-profile households keep
                their lists separate.
            name: Display name for the list.

        Returns:
            A new CustomList instance.
        """
        return cls(
            id=ListId.generate(),
            profile_id=profile_id,
            name=name,
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
