"""Use case: TMDB lookup that powers the "Request a title" dialog.

Accepts any of TMDB id / IMDb id / TMDB URL / IMDb URL / plain title
and returns a single list of picker candidates. The user picks one
card and the frontend POSTs the chosen ``(tmdb_id, media_type)`` to
``/catalog-requests`` to create the actual request.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from src.modules.media.application.dtos.tmdb_lookup_dtos import (
    SearchTmdbTitlesInput,
    SearchTmdbTitlesOutput,
    TmdbLookupCandidate,
)

if TYPE_CHECKING:
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.metadata.application.ports.metadata_provider_port import (
        MetadataProvider,
        SearchCandidate,
    )


# TMDB URL example: https://www.themoviedb.org/movie/603-the-matrix
_TMDB_URL_RE = re.compile(
    r"themoviedb\.org/(?P<kind>movie|tv)/(?P<id>\d+)",
    re.IGNORECASE,
)
# IMDb URL example: https://www.imdb.com/title/tt0133093/
_IMDB_URL_RE = re.compile(
    r"imdb\.com/title/(?P<id>tt\d{6,})",
    re.IGNORECASE,
)
# Bare IMDb id, the canonical "tt" prefix + 7+ digits.
_IMDB_BARE_RE = re.compile(r"^tt\d{6,}$", re.IGNORECASE)
# Bare numeric TMDB id.
_TMDB_BARE_RE = re.compile(r"^\d+$")


@dataclass(frozen=True)
class _TmdbIdQuery:
    """A resolved TMDB numeric id, from a URL or a bare number.

    ``media_type`` is ``None`` for an ambiguous bare numeric (TMDB ids are
    not unique across the movie / tv namespaces), so the caller fetches both.
    """

    tmdb_id: int
    media_type: Literal["movie", "tv"] | None = None
    kind: Literal["tmdb_id"] = "tmdb_id"


@dataclass(frozen=True)
class _ImdbIdQuery:
    """A canonical IMDb id (``tt...``)."""

    imdb_id: str
    kind: Literal["imdb_id"] = "imdb_id"


@dataclass(frozen=True)
class _TextQuery:
    """A cleaned free-text search query."""

    text: str
    kind: Literal["text"] = "text"


# Discriminated union on ``kind`` — each branch carries only its own fields,
# so mypy narrows the payload without per-branch ``| None`` widening.
_ParsedQuery = _TmdbIdQuery | _ImdbIdQuery | _TextQuery


def parse_lookup_query(raw: str) -> _ParsedQuery | None:
    """Detect which shape ``raw`` is and return the routing hint.

    Returns ``None`` when ``raw`` is empty / whitespace-only — the
    caller short-circuits to an empty result before paying for any
    TMDB call.
    """
    cleaned = raw.strip()
    if not cleaned:
        return None

    if url_match := _TMDB_URL_RE.search(cleaned):
        kind = url_match.group("kind").lower()
        return _TmdbIdQuery(
            tmdb_id=int(url_match.group("id")),
            media_type="movie" if kind == "movie" else "tv",
        )

    if imdb_match := _IMDB_URL_RE.search(cleaned):
        return _ImdbIdQuery(imdb_id=imdb_match.group("id").lower())

    if _IMDB_BARE_RE.fullmatch(cleaned):
        return _ImdbIdQuery(imdb_id=cleaned.lower())

    if _TMDB_BARE_RE.fullmatch(cleaned):
        # Bare numeric — media_type unset flags "try both" (see docstring).
        return _TmdbIdQuery(tmdb_id=int(cleaned))

    return _TextQuery(text=cleaned)


class SearchTmdbTitlesUseCase:
    """Resolve a free-form query into TMDB picker candidates.

    The result list is short (≤ 2 for by-id branches, ≤ ``2*limit``
    for the text branch) and intentionally not paginated — the
    request dialog renders all hits inline.

    Args:
        metadata_provider: TMDB-side metadata port. Same singleton
            already wired into the rest of the media BC.
    """

    def __init__(
        self,
        metadata_provider: MetadataProvider,
        uow_factory: MediaUnitOfWorkFactory,
    ) -> None:
        self._provider = metadata_provider
        self._uow_factory = uow_factory

    async def execute(self, input_dto: SearchTmdbTitlesInput) -> SearchTmdbTitlesOutput:
        """Parse ``input_dto.query`` and return the matching TMDB candidates."""
        parsed = parse_lookup_query(input_dto.query)
        if parsed is None:
            return SearchTmdbTitlesOutput(query="", kind="text", candidates=[])

        if parsed.kind == "tmdb_id":
            candidates = await self._fetch_by_tmdb_id(
                parsed.tmdb_id,
                parsed.media_type,
            )
            return SearchTmdbTitlesOutput(
                query=input_dto.query.strip(),
                kind="tmdb_id",
                candidates=await self._mark_in_catalog(candidates),
            )

        if parsed.kind == "imdb_id":
            results = await self._provider.find_by_imdb_id(parsed.imdb_id)
            return SearchTmdbTitlesOutput(
                query=parsed.imdb_id,
                kind="imdb_id",
                candidates=await self._mark_in_catalog([_to_dto(c) for c in results]),
            )

        # text branch
        text = parsed.text
        limit = max(1, min(input_dto.limit, 20))
        movies, series = await asyncio.gather(
            self._provider.find_movie_candidates(text, year=None, limit=limit),
            self._provider.find_series_candidates(text, year=None, limit=limit),
        )
        return SearchTmdbTitlesOutput(
            query=text,
            kind="text",
            candidates=await self._mark_in_catalog(
                [_to_dto(c) for c in (*movies, *series)],
            ),
        )

    async def _mark_in_catalog(
        self,
        candidates: list[TmdbLookupCandidate],
    ) -> list[TmdbLookupCandidate]:
        """Flag candidates whose ``tmdb_id`` is already hosted locally.

        One batch query per kind against the catalog, so the picker can
        disable "request" for titles that are already available
        (regardless of profile library access — "in the catalog" is a
        household-level fact here).
        """
        if not candidates:
            return candidates
        movie_ids = [c.tmdb_id for c in candidates if c.media_type == "movie"]
        series_ids = [c.tmdb_id for c in candidates if c.media_type == "tv"]
        async with self._uow_factory() as uow:
            movies = await uow.movies.find_by_tmdb_ids(movie_ids) if movie_ids else {}
            series = await uow.series.find_by_tmdb_ids(series_ids) if series_ids else {}
        return [
            replace(
                candidate,
                in_catalog=candidate.tmdb_id
                in (movies if candidate.media_type == "movie" else series),
            )
            for candidate in candidates
        ]

    async def _fetch_by_tmdb_id(
        self,
        tmdb_id: int,
        media_type: Literal["movie", "tv"] | None,
    ) -> list[TmdbLookupCandidate]:
        """Resolve a TMDB id; ambiguous bare numerics try both kinds."""
        if media_type == "movie":
            hit = await self._provider.get_movie_summary_by_id(tmdb_id)
            return [_to_dto(hit)] if hit else []
        if media_type == "tv":
            hit = await self._provider.get_series_summary_by_id(tmdb_id)
            return [_to_dto(hit)] if hit else []

        movie_hit, series_hit = await asyncio.gather(
            self._provider.get_movie_summary_by_id(tmdb_id),
            self._provider.get_series_summary_by_id(tmdb_id),
        )
        results: list[TmdbLookupCandidate] = []
        if movie_hit is not None:
            results.append(_to_dto(movie_hit))
        if series_hit is not None:
            results.append(_to_dto(series_hit))
        return results


def _to_dto(candidate: SearchCandidate) -> TmdbLookupCandidate:
    return TmdbLookupCandidate(
        tmdb_id=candidate.tmdb_id,
        media_type=candidate.media_type,
        title=candidate.title,
        year=candidate.year,
        overview=candidate.overview,
        poster_url=candidate.poster_url,
    )


__all__ = ["SearchTmdbTitlesUseCase", "parse_lookup_query"]
