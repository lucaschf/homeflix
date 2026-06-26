"""Custom list DTOs for application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.collections.application.ports.media_lookup_port import MediaSummary
    from src.modules.collections.domain.entities import CustomList, CustomListItem
    from src.shared_kernel.value_objects import MediaType


@dataclass(frozen=True)
class CreateCustomListInput:
    """Input for CreateCustomListUseCase."""

    profile_id: str
    name: str
    description: str | None = None


@dataclass(frozen=True)
class CustomListOutput:
    """Output representing a custom list."""

    id: str
    name: str
    item_count: int
    created_at: str
    updated_at: str
    description: str | None = None

    @classmethod
    def from_entity(cls, entity: CustomList) -> CustomListOutput:
        """Create output DTO from a CustomList entity."""
        return cls(
            id=str(entity.id),
            name=entity.name.value,
            item_count=entity.item_count,
            created_at=entity.created_at.isoformat(),
            updated_at=entity.updated_at.isoformat(),
            description=entity.description,
        )


@dataclass(frozen=True)
class RenameCustomListInput:
    """Input for RenameCustomListUseCase."""

    profile_id: str
    list_id: str
    name: str
    description: str | None = None


@dataclass(frozen=True)
class DeleteCustomListInput:
    """Input for DeleteCustomListUseCase."""

    profile_id: str
    list_id: str


@dataclass(frozen=True)
class AddItemToCustomListInput:
    """Input for AddItemToCustomListUseCase."""

    profile_id: str
    list_id: str
    media_id: str
    media_type: MediaType


@dataclass(frozen=True)
class RemoveItemFromCustomListInput:
    """Input for RemoveItemFromCustomListUseCase."""

    profile_id: str
    list_id: str
    media_id: str


@dataclass(frozen=True)
class GetCustomListItemsInput:
    """Input for GetCustomListItemsUseCase."""

    profile_id: str
    list_id: str
    lang: str = "en"


@dataclass(frozen=True)
class CustomListItemOutput:
    """Output representing an item in a custom list with media metadata."""

    media_id: str
    media_type: MediaType
    title: str
    poster_path: str | None
    position: int
    added_at: str
    year: int | None = None
    runtime_seconds: int | None = None
    genres: tuple[str, ...] = ()
    resolution: str | None = None
    hdr: bool = False
    # Watched fraction in [0, 1], or None when there's no progress.
    progress: float | None = None

    @classmethod
    def from_entity(
        cls,
        entity: CustomListItem,
        summary: MediaSummary,
        progress: float | None = None,
    ) -> CustomListItemOutput:
        """Create output DTO from a CustomListItem entity + media summary."""
        return cls(
            media_id=entity.media_id.value,
            media_type=entity.media_type,
            title=summary.title,
            poster_path=summary.poster_path,
            position=entity.position,
            added_at=entity.added_at.isoformat(),
            year=summary.year,
            runtime_seconds=summary.runtime_seconds,
            genres=summary.genres,
            resolution=summary.resolution,
            hdr=summary.hdr,
            progress=progress,
        )
