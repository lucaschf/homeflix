"""Column <-> ArtworkColumns conversion for the mirror finders (ADR-029).

Shared by the movie and series repositories so the raw poster/backdrop/
logo string columns are wrapped into (and unwrapped from) an
``ArtworkColumns`` value object in exactly one place.

The ``*_localized_*`` helpers do the same for the per-locale artwork
inside the ``localized`` JSON blob (ADR-023): they are the only place
that builds a JSON path into that blob for writing, and every field
name comes from ``LocalizedField`` — the read-side ``json_extract``
in ``_genre_helpers`` is the precedent for touching the blob from SQL.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select, true, update

from src.modules.media.domain.repositories.artwork_mirror_repository import RemoteArtworkRow
from src.modules.media.domain.value_objects import ArtworkColumns, ImageUrl
from src.modules.media.domain.value_objects.localized_metadata import LocalizedField

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# A locale key must be usable verbatim as a quoted JSON object key in a
# SQLite JSON path (``$."pt-BR".poster_path``). ``LanguageTag`` allows
# letters, digits and hyphens; quotes and dots are what would break the
# path, and the length bound mirrors BCP 47's practical maximum.
_LOCALE_KEY_PATTERN = re.compile(r"[A-Za-z0-9-]{2,35}")

_LOCALIZED_ARTWORK_FIELDS = (
    LocalizedField.POSTER_PATH,
    LocalizedField.BACKDROP_PATH,
    LocalizedField.LOGO_PATH,
)


def to_artwork_columns(
    poster: str | None,
    backdrop: str | None,
    logo: str | None,
) -> ArtworkColumns:
    """Wrap raw column strings into an ``ArtworkColumns`` value object."""
    return ArtworkColumns(
        poster=ImageUrl(poster) if poster else None,
        backdrop=ImageUrl(backdrop) if backdrop else None,
        logo=ImageUrl(logo) if logo else None,
    )


def to_still_columns(thumbnail: str | None) -> ArtworkColumns:
    """Wrap a raw episode-still string into an ``ArtworkColumns`` (``still`` set)."""
    return ArtworkColumns(still=ImageUrl(thumbnail) if thumbnail else None)


def artwork_column_values(artwork: ArtworkColumns) -> dict[str, str | None]:
    """Unwrap an ``ArtworkColumns`` into a ``{column: value}`` update map."""
    return {
        "poster_path": artwork.poster.value if artwork.poster else None,
        "backdrop_path": artwork.backdrop.value if artwork.backdrop else None,
        "logo_path": artwork.logo.value if artwork.logo else None,
    }


def localized_artwork_path(locale: str, field: LocalizedField) -> str:
    """Return the JSON path ``$."<locale>".<field>`` for a localized artwork field.

    ``locale`` is the raw key of the ``localized`` blob and is validated,
    never rewritten: stripping characters (as the read-side sort helper
    does) would make a write land on a *different* key, silently adding
    a locale entry instead of updating the one the finder read.

    Raises:
        ValueError: when ``locale`` is not a safe JSON object key.
    """
    if not _LOCALE_KEY_PATTERN.fullmatch(locale):
        raise ValueError(f"unsafe locale key for a JSON path: {locale!r}")
    return f'$."{locale}".{field.value}'


async def fetch_remote_localized_artwork(
    session: AsyncSession,
    model: Any,
    limit: int,
) -> list[RemoteArtworkRow]:
    """Return up to ``limit`` (title, locale) pairs with a remote localized artwork URL.

    Walks the ``localized`` blob with SQLite's ``json_each`` so each
    locale becomes its own row, projecting only the external id, the
    locale key and the three artwork fields — the aggregate is never
    loaded. ``json_valid`` keeps a malformed blob from aborting the
    whole query, and a ``NULL`` blob simply yields no rows. The explicit
    ``JOIN ... ON 1 = 1`` is how SQLAlchemy correlates the table-valued
    function with its source row. SQLite-specific, like the
    ``json_extract`` sort key in ``_genre_helpers``.
    """
    entries = func.json_each(model.localized).table_valued("key", "value", name="loc")
    poster, backdrop, logo = (
        func.json_extract(entries.c.value, f"$.{field.value}")
        for field in _LOCALIZED_ARTWORK_FIELDS
    )
    stmt = (
        select(model.external_id, entries.c.key, poster, backdrop, logo)
        .select_from(model)
        .join(entries, true())
        .where(
            model.deleted_at.is_(None),
            func.json_valid(model.localized),
            or_(poster.like("http%"), backdrop.like("http%"), logo.like("http%")),
        )
        .order_by(model.id.asc(), entries.c.key.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [
        RemoteArtworkRow(
            media_id=external_id,
            artwork=to_artwork_columns(poster_url, backdrop_url, logo_url),
            locale=locale,
        )
        for external_id, locale, poster_url, backdrop_url, logo_url in result.all()
    ]


async def update_localized_artwork(
    session: AsyncSession,
    model: Any,
    external_id: str,
    locale: str,
    artwork: ArtworkColumns,
) -> None:
    """Rewrite one locale's artwork fields inside the ``localized`` blob.

    A single ``json_set`` touching only the non-``None`` fields, so a
    concurrent enrichment that rewrites title/synopsis/other locales is
    never reverted; the same field stays last-writer-wins, like the
    top-level column update. No-op when there is nothing to write or the
    blob is ``NULL`` (``json_set(NULL, ...)`` is ``NULL`` anyway, and
    the guard keeps ``updated_at`` from bumping for nothing).

    Raises:
        ValueError: when ``locale`` cannot be used as a JSON path key.
    """
    args: list[Any] = []
    for field, value in (
        (LocalizedField.POSTER_PATH, artwork.poster),
        (LocalizedField.BACKDROP_PATH, artwork.backdrop),
        (LocalizedField.LOGO_PATH, artwork.logo),
    ):
        if value is not None:
            args.extend((localized_artwork_path(locale, field), value.value))
    if not args:
        return
    await session.execute(
        update(model)
        .where(model.external_id == external_id, model.localized.is_not(None))
        .values(localized=func.json_set(model.localized, *args))
    )


__all__ = [
    "artwork_column_values",
    "fetch_remote_localized_artwork",
    "localized_artwork_path",
    "to_artwork_columns",
    "to_still_columns",
    "update_localized_artwork",
]
