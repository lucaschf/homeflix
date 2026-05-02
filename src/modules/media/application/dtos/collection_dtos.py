"""DTOs for the Collection Detail use case."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GetCollectionByTmdbIdInput:
    """Input for ``GetCollectionByTmdbIdUseCase``.

    Attributes:
        tmdb_id: TMDB collection id (e.g. ``8091`` for Alien
            Collection).
        lang: BCP-47 tag for localized titles, overview, and the
            preferred poster language. Defaults to ``"en"`` to match
            the rest of the read-side use cases.
    """

    tmdb_id: int
    lang: str = "en"


@dataclass(frozen=True)
class CollectionPartOutput:
    """A single member title of a collection, merged with local state.

    The Collection Detail page renders one ``FilmRow`` per part. The
    DTO stitches together TMDB metadata, the local catalog row (when
    the title is hosted), and the catalog-request status (when the
    user has clicked "Solicitar inclusão" / "Avisar quando chegar")
    into a flat shape so the UI doesn't need to cross-reference
    sources.

    Attributes:
        tmdb_id: TMDB movie id of the part.
        title: Display title.
        year: Release year.
        synopsis: Plot overview.
        poster_url: Full TMDB poster URL - always populated, even
            when the title is in catalog, since the UI prefers
            TMDB's normalized cover for the franchise grid.
        backdrop_url: Full TMDB backdrop URL.
        rating: TMDB ``vote_average`` (0-10) when available.
        runtime_seconds: Runtime in seconds, ``None`` when neither
            TMDB nor local data carries it.
        runtime_formatted: Pre-formatted ``HH:MM:SS`` string for the
            UI, ``None`` when no runtime is known.
        in_catalog: ``True`` when the title is hosted locally and
            playable; ``False`` otherwise (drives the missing-state
            visual treatment).
        movie_id: External movie id (``mov_xxx``) when in catalog,
            so the FilmRow's "Detalhes →" CTA can link to the
            existing Movie Detail page.
        local_poster_path: Local poster URL when in catalog. Falls
            back to ``poster_url`` (TMDB) so the UI doesn't have to
            null-check.
        local_backdrop_path: Local backdrop URL when in catalog.
        is_requested: ``True`` when the user has registered a
            catalog inclusion request for this title. Always
            ``False`` for parts that are already in catalog (the
            request is implicitly fulfilled).
        notify_on_arrival: ``True`` when the user has subscribed to
            the arrival notification.
    """

    tmdb_id: int
    title: str
    year: int | None
    synopsis: str | None
    poster_url: str | None
    backdrop_url: str | None
    rating: float | None
    runtime_seconds: int | None
    runtime_formatted: str | None
    in_catalog: bool
    movie_id: str | None
    local_poster_path: str | None
    local_backdrop_path: str | None
    is_requested: bool
    notify_on_arrival: bool


@dataclass(frozen=True)
class CollectionDetailOutput:
    """Output for ``GetCollectionByTmdbIdUseCase``.

    Attributes:
        tmdb_id: TMDB collection id.
        name: Display name.
        overview: Long-form description of the franchise.
        poster_url: Collection-level poster URL.
        backdrop_url: Collection-level backdrop URL.
        total_parts: Number of parts TMDB knows about.
        available_parts: Subset hosted locally (``in_catalog=True``).
        missing_parts: ``total_parts - available_parts``.
        parts: Member titles ordered by release year ascending. Parts
            with an unknown year are placed last in TMDB's original
            order so the page never blows up on a single missing
            ``release_date``.
    """

    tmdb_id: int
    name: str
    overview: str | None
    poster_url: str | None
    backdrop_url: str | None
    total_parts: int
    available_parts: int
    missing_parts: int
    parts: list[CollectionPartOutput]


__all__ = [
    "CollectionDetailOutput",
    "CollectionPartOutput",
    "GetCollectionByTmdbIdInput",
]
