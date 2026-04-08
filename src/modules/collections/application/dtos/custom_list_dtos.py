"""Custom list DTOs for application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.modules.collections.domain.entities import CustomList, CustomListItem


@dataclass(frozen=True)
class CreateCustomListInput:
    """Input for CreateCustomListUseCase.

    Attributes:
        name: Display name for the new list.
    """

    name: str


@dataclass(frozen=True)
class CustomListOutput:
    """Output representing a custom list.

    Attributes:
        id: External ID (lst_xxx format).
        name: Display name of the list.
        item_count: Number of items in the list.
        created_at: ISO timestamp when the list was created.
        updated_at: ISO timestamp when the list was last updated.
    """

    id: str
    name: str
    item_count: int
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, entity: CustomList) -> CustomListOutput:
        """Create output DTO from a CustomList entity.

        Args:
            entity: The CustomList domain entity.

        Returns:
            CustomListOutput DTO.
        """
        return cls(
            id=str(entity.id),
            name=entity.name,
            item_count=entity.item_count,
            created_at=entity.created_at.isoformat(),
            updated_at=entity.updated_at.isoformat(),
        )


@dataclass(frozen=True)
class RenameCustomListInput:
    """Input for RenameCustomListUseCase.

    Attributes:
        list_id: External ID of the list.
        name: New display name.
    """

    list_id: str
    name: str


@dataclass(frozen=True)
class AddItemToCustomListInput:
    """Input for AddItemToCustomListUseCase.

    Attributes:
        list_id: External ID of the list.
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media ("movie" or "series").
    """

    list_id: str
    media_id: str
    media_type: Literal["movie", "series"]


@dataclass(frozen=True)
class RemoveItemFromCustomListInput:
    """Input for RemoveItemFromCustomListUseCase.

    Attributes:
        list_id: External ID of the list.
        media_id: External ID of the media.
    """

    list_id: str
    media_id: str


@dataclass(frozen=True)
class GetCustomListItemsInput:
    """Input for GetCustomListItemsUseCase.

    Attributes:
        list_id: External ID of the list.
        lang: Language code for localized metadata.
    """

    list_id: str
    lang: str = "en"


@dataclass(frozen=True)
class CustomListItemOutput:
    """Output representing an item in a custom list with media metadata.

    Attributes:
        media_id: External ID of the media.
        media_type: Type of media.
        title: Display title (localized).
        poster_path: URL to poster image.
        position: Ordering position within the list.
        added_at: ISO timestamp when added to the list.
    """

    media_id: str
    media_type: str
    title: str
    poster_path: str | None
    position: int
    added_at: str

    @classmethod
    def from_entity(
        cls,
        entity: CustomListItem,
        title: str,
        poster_path: str | None,
    ) -> CustomListItemOutput:
        """Create output DTO from a CustomListItem entity with metadata.

        Args:
            entity: The CustomListItem domain entity.
            title: Localized display title.
            poster_path: URL to poster image.

        Returns:
            CustomListItemOutput DTO.
        """
        return cls(
            media_id=entity.media_id,
            media_type=entity.media_type,
            title=title,
            poster_path=poster_path,
            position=entity.position,
            added_at=entity.added_at.isoformat(),
        )
