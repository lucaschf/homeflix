"""Shared projection of custom-list items into output DTOs.

Used by the owner read (``GetCustomListItemsUseCase``), the shared
preview, and the followed-list read. Centralizes the media-summary
join, the caller's watch-progress join, and — for follower reads — the
per-profile library-access filter that keeps a shared list from
becoming an access-control bypass (ADR-010).
"""

from collections.abc import Sequence

from src.modules.collections.application.dtos import CustomListItemOutput
from src.modules.collections.application.ports import MediaLookupPort, ProgressLookupPort
from src.modules.collections.domain.entities import CustomListItem
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.library_id import LibraryId


async def project_items(
    items: Sequence[CustomListItem],
    *,
    media_lookup: MediaLookupPort,
    progress_lookup: ProgressLookupPort,
    lang: str,
    profile_id: str,
    allowed_library_ids: Sequence[LibraryId] | None,
) -> tuple[list[CustomListItemOutput], int]:
    """Join items with media + progress, optionally filtering by access.

    Args:
        items: The list's items, already ordered by position.
        media_lookup: Port resolving media display metadata.
        progress_lookup: Port resolving the caller's watch progress.
        lang: Language for localized titles/genres.
        profile_id: The caller's profile id (whose progress is shown).
        allowed_library_ids: When ``None`` the caller owns the list and
            sees everything (no filter, ``hidden_count`` is ``0``). When
            a (possibly empty) sequence, the caller is a follower and an
            item is hidden unless its media's library is in the set.

    Returns:
        ``(outputs, hidden_count)`` — the visible item DTOs (ordered as
        given) and the number of items dropped by the access filter.
        Items whose media no longer resolves are silently skipped and
        are *not* counted as hidden (they're gone, not restricted).
    """
    if not items:
        return [], 0

    movie_ids = [i.media_id.as_movie_id() for i in items if i.media_type == MediaType.MOVIE]
    series_ids = [i.media_id.as_series_id() for i in items if i.media_type == MediaType.SERIES]
    summaries = await media_lookup.get_many(movie_ids, series_ids, lang)

    # Progress only exists for movies (series progress lives on
    # episodes — deferred), so look up movie ids only.
    movie_id_strs = [i.media_id.value for i in items if i.media_type == MediaType.MOVIE]
    progress = await progress_lookup.get_progress(movie_id_strs, profile_id=profile_id)

    allowed = None if allowed_library_ids is None else {lib.value for lib in allowed_library_ids}

    outputs: list[CustomListItemOutput] = []
    hidden_count = 0
    for item in items:
        summary = summaries.get((item.media_type, item.media_id.value))
        if summary is None:
            # Media was removed from the catalog — skip, don't count.
            continue
        if allowed is not None and summary.library_id not in allowed:
            hidden_count += 1
            continue
        outputs.append(
            CustomListItemOutput.from_entity(
                entity=item,
                summary=summary,
                progress=progress.get(item.media_id.value),
            )
        )
    return outputs, hidden_count


__all__ = ["project_items"]
