"""Cast list JSON (de)serialization.

Single source of truth for the shape stored in the ``cast`` Text
column on every media-owning model (movies and series share the
schema). Centralizing the helpers keeps the legacy-tolerant decode
path from drifting between mappers.
"""

from __future__ import annotations

import json

from src.modules.media.domain.value_objects import CastMember


def serialize_cast(cast: list[CastMember]) -> str | None:
    """Serialize the cast list to the JSON shape stored on disk.

    Current shape:
    ``[{"name": "...", "profile_path": "...", "role": "...", "tmdb_id": 123}, ...]``.

    Always written this way; older shapes (``["Name1", "Name2"]`` and
    the dict shape without ``tmdb_id``) are only *read* by
    :func:`deserialize_cast` and get converted on the next save.
    """
    if not cast:
        return None
    payload = [
        {
            "name": m.name,
            "profile_path": m.profile_path,
            "role": m.role,
            "tmdb_id": m.tmdb_id,
        }
        for m in cast
    ]
    return json.dumps(payload, ensure_ascii=False)


def deserialize_cast(raw: str | None) -> list[CastMember]:
    """Reconstruct the cast list from the JSON column.

    Accepts every historic shape so rows enriched at any point still
    load: legacy ``list[str]`` (initials-only fallback), the dict
    shape without ``tmdb_id`` (no bio link on the actor page —
    degrades to a name-only flow), and the current dict shape with
    ``tmdb_id``. The next save migrates the row to the current shape
    implicitly.

    Tolerant of malformed payloads at the storage boundary: a JSON
    value that is not a list (drift from a future migration, manual
    DB edit) collapses to an empty cast rather than iterating dict
    keys as if they were entries; dict entries with no usable
    ``name`` are skipped so the UI never renders empty cards. A
    non-int ``tmdb_id`` (string, float, malformed import) is dropped
    silently rather than raising.
    """
    if not raw:
        return []
    items = json.loads(raw)
    if not isinstance(items, list):
        return []
    members: list[CastMember] = []
    for item in items:
        if isinstance(item, str):
            name = item.strip()
            if name:
                members.append(CastMember(name=name))
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            raw_tmdb_id = item.get("tmdb_id")
            tmdb_id = raw_tmdb_id if isinstance(raw_tmdb_id, int) else None
            members.append(
                CastMember(
                    name=name,
                    profile_path=item.get("profile_path") or None,
                    role=item.get("role") or None,
                    tmdb_id=tmdb_id,
                )
            )
    return members


__all__ = ["deserialize_cast", "serialize_cast"]
