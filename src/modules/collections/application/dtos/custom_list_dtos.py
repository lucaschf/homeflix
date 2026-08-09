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
    """Output representing a custom list.

    The same shape serves both the caller's *own* lists and the lists
    they *follow*. ``is_shared`` is meaningful on owned rows (a token
    exists); ``is_followed`` + ``owner_name`` are meaningful on
    followed rows. Followed rows are read-only and don't count against
    the owner's ``MAX_LISTS`` quota.
    """

    id: str
    name: str
    item_count: int
    created_at: str
    updated_at: str
    description: str | None = None
    is_shared: bool = False
    is_followed: bool = False
    owner_name: str | None = None

    @classmethod
    def from_entity(
        cls,
        entity: CustomList,
        *,
        is_followed: bool = False,
        owner_name: str | None = None,
    ) -> CustomListOutput:
        """Create output DTO from a CustomList entity.

        Args:
            entity: The list to serialize.
            is_followed: ``True`` when this row is a list the caller
                follows (not owns).
            owner_name: Display name of the owner — set for followed
                rows, ``None`` for owned rows.
        """
        return cls(
            id=str(entity.id),
            name=entity.name.value,
            item_count=entity.item_count,
            created_at=entity.created_at.isoformat(),
            updated_at=entity.updated_at.isoformat(),
            description=entity.description,
            # ``is_shared`` is an owner-side flag ("I shared this"); a
            # followed row is never the caller's own share.
            is_shared=entity.is_shared and not is_followed,
            is_followed=is_followed,
            owner_name=owner_name,
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
class ReorderCustomListItemsInput:
    """Input for ReorderCustomListItemsUseCase."""

    profile_id: str
    list_id: str
    media_ids: tuple[str, ...]


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


@dataclass(frozen=True)
class CustomListItemsOutput:
    """Items in a custom list plus the count hidden by profile access.

    ``hidden_count`` is always ``0`` for the owner's own list (they see
    everything they own) and only rises on a *followed* list whose
    owner referenced titles the follower's profile can't see.
    """

    items: tuple[CustomListItemOutput, ...]
    hidden_count: int = 0


@dataclass(frozen=True)
class ShareCustomListInput:
    """Input for ShareCustomListUseCase (mint/return a share token)."""

    profile_id: str
    list_id: str


@dataclass(frozen=True)
class ShareCustomListOutput:
    """Output of sharing: the token plus its client-side landing path."""

    token: str
    url_path: str


@dataclass(frozen=True)
class RevokeCustomListShareInput:
    """Input for RevokeCustomListShareUseCase."""

    profile_id: str
    list_id: str


@dataclass(frozen=True)
class GetSharedListPreviewInput:
    """Input for GetSharedListPreviewUseCase (read-only, by token)."""

    profile_id: str
    token: str
    lang: str = "en"


@dataclass(frozen=True)
class SharedListMetaOutput:
    """Owner-facing metadata of a shared list in the preview response."""

    id: str
    name: str
    description: str | None
    owner_name: str | None
    item_count: int


@dataclass(frozen=True)
class SharedListPreviewOutput:
    """Read-only preview of a shared list, filtered by caller access."""

    list: SharedListMetaOutput
    items: tuple[CustomListItemOutput, ...]
    hidden_count: int
    is_following: bool


@dataclass(frozen=True)
class FollowSharedListInput:
    """Input for FollowSharedListUseCase (follow by token)."""

    profile_id: str
    token: str


@dataclass(frozen=True)
class UnfollowCustomListInput:
    """Input for UnfollowCustomListUseCase."""

    profile_id: str
    list_id: str
