"""Shared helpers for projecting raw `genres` / `localized` columns.

Used by both ``SQLAlchemyMovieRepository.list_genre_rows`` and
``SQLAlchemySeriesRepository.list_genre_rows`` to parse the
comma-separated `genres` column and the per-row `localized` JSON
without going through the entity mapper. Lives next to the repos
because the parsing logic mirrors the column shape exactly — keeping
it here means a column-format change touches one place instead of
two.
"""

import json


def split_genres(raw: str | None) -> list[str]:
    """Parse the comma-separated ``genres`` column into a clean list.

    Returns an empty list for ``None`` or empty input. Whitespace
    around individual genre names is stripped.
    """
    if not raw:
        return []
    return [g.strip() for g in raw.split(",") if g.strip()]


def localized_genres_for(localized_json: str | None, lang: str) -> list[str]:
    """Pull the localized genres array for ``lang`` from the ``localized`` JSON.

    The ``localized`` column is a JSON-encoded dict like
    ``{"pt-BR": {"title": "...", "genres": ["Ação", "Comédia"]}}``.
    This helper safely returns an empty list when the JSON is
    missing, malformed, doesn't carry the requested language, or
    doesn't have a ``genres`` array — the consumer treats an empty
    result as "no translation available" and falls back to the
    canonical names positionally.
    """
    if not localized_json:
        return []
    try:
        data = json.loads(localized_json)
    except (TypeError, ValueError):
        return []
    lang_block = data.get(lang) if isinstance(data, dict) else None
    if not isinstance(lang_block, dict):
        return []
    raw = lang_block.get("genres")
    if not isinstance(raw, list):
        return []
    return [str(g) for g in raw]


__all__ = ["localized_genres_for", "split_genres"]
