"""Shared projection of custom-list items into output DTOs.

Used by the owner read (``GetCustomListItemsUseCase``), the shared
preview, and the followed-list read. Centralizes the media-summary
join, the caller's watch-progress join, and the caller's viewing policy
— library access and maturity limit — that keeps a list from becoming
an access-control bypass (ADR-010, ADR-035). The watchlist read applies
the same per-summary rule through :func:`permits_summary`.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.collections.application.dtos import CustomListItemOutput
from src.modules.collections.application.ports import (
    MediaLookupPort,
    MediaSummary,
    ProgressLookupPort,
)
from src.modules.collections.domain.entities import CustomListItem
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.library_id import LibraryId


@dataclass(frozen=True)
class ProjectedItems:
    """The items of a list as the caller may see them.

    Attributes:
        items: The emitted item DTOs, in list order.
        hidden_count: Items dropped because the caller's profile does
            not reach their library. The only count a response exposes.
        withheld_by_maturity: Items in a reachable library dropped by
            the caller's maturity limit. Internal — never serialized, so
            a limited profile cannot learn how many titles were withheld
            from it; callers only use it to adjust a stored item count.
    """

    items: list[CustomListItemOutput]
    hidden_count: int
    withheld_by_maturity: int


async def project_items(
    items: Sequence[CustomListItem],
    *,
    media_lookup: MediaLookupPort,
    progress_lookup: ProgressLookupPort,
    lang: str,
    profile_id: str,
    policy: ViewingPolicy,
) -> ProjectedItems:
    """Join items with media + progress, filtering by the caller's policy.

    Each item goes through the checks in a fixed order, and the first
    one that fails decides what happens to it:

    1. Its media no longer resolves (removed from the catalog): skipped,
       not counted — it is gone, not restricted.
    2. The policy does not reach its library: counted in
       ``hidden_count``.
    3. The policy's maturity limit does not allow it: counted in
       ``withheld_by_maturity`` only.
    4. Otherwise it is emitted.

    Under a maturity limit the emitted ``position`` is renumbered
    ``0..n-1`` among the emitted items, so gaps cannot reveal where a
    withheld title sat. Without a limit the stored position is kept.

    Args:
        items: The list's items, already ordered by position.
        media_lookup: Port resolving media display metadata.
        progress_lookup: Port resolving the caller's watch progress.
        lang: Language for localized titles/genres.
        profile_id: The caller's profile id (whose progress is shown).
        policy: The caller's viewing policy — the same for the owner, a
            follower and a preview.

    Returns:
        The emitted items and the counts of items dropped by each axis.
    """
    if not items:
        return ProjectedItems(items=[], hidden_count=0, withheld_by_maturity=0)

    movie_ids = [i.media_id.as_movie_id() for i in items if i.media_type == MediaType.MOVIE]
    series_ids = [i.media_id.as_series_id() for i in items if i.media_type == MediaType.SERIES]
    summaries = await media_lookup.get_many(movie_ids, series_ids, lang)

    # Progress only exists for movies (series progress lives on
    # episodes — deferred), so look up movie ids only.
    movie_id_strs = [i.media_id.value for i in items if i.media_type == MediaType.MOVIE]
    progress = await progress_lookup.get_progress(movie_id_strs, profile_id=profile_id)

    outputs: list[CustomListItemOutput] = []
    hidden_count = 0
    withheld_by_maturity = 0
    for item in items:
        summary = summaries.get((item.media_type, item.media_id.value))
        if summary is None:
            # Media was removed from the catalog — skip, don't count.
            continue
        if not _permits_library(policy, summary.library_id):
            hidden_count += 1
            continue
        if not policy.permits_maturity(summary.minimum_age):
            withheld_by_maturity += 1
            continue
        output = CustomListItemOutput.from_entity(
            entity=item,
            summary=summary,
            progress=progress.get(item.media_id.value),
        )
        if policy.restricts_maturity:
            output = replace(output, position=len(outputs))
        outputs.append(output)
    return ProjectedItems(
        items=outputs,
        hidden_count=hidden_count,
        withheld_by_maturity=withheld_by_maturity,
    )


def permits_summary(policy: ViewingPolicy, summary: MediaSummary) -> bool:
    """Whether ``policy`` lets the caller see the media behind ``summary``.

    Both axes, with no distinction between them — for reads that drop a
    restricted item without counting it.

    Args:
        policy: The caller's viewing policy.
        summary: The media's display data, carrying its library and age.

    Returns:
        ``True`` only when the library and the maturity limit both allow it.
    """
    return _permits_library(policy, summary.library_id) and policy.permits_maturity(
        summary.minimum_age
    )


def _permits_library(policy: ViewingPolicy, library_id: str | None) -> bool:
    """Whether ``policy`` reaches the library an item's media lives in.

    ``MediaSummary.library_id`` is a raw string that may be absent,
    malformed, or padded with whitespace ``LibraryId`` would strip. None
    of these is the exact id the catalog's SQL gate matches, so all are
    denied instead of raised: the item is hidden, not the whole read.

    Args:
        policy: The caller's viewing policy.
        library_id: The media's ``lib_xxx`` id, or ``None`` when unknown.

    Returns:
        ``True`` only when the id is canonical and the policy permits it.
    """
    if library_id is None:
        return False
    try:
        typed = LibraryId(library_id)
    except DomainValidationException:
        return False
    return typed.value == library_id and policy.permits_library(typed)


__all__ = ["ProjectedItems", "permits_summary", "project_items"]
