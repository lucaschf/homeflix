"""GetCollectionByTmdbIdUseCase — TMDB collection enriched with local state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.collection_dtos import (
    CollectionDetailOutput,
    CollectionPartOutput,
    GetCollectionByTmdbIdInput,
)

if TYPE_CHECKING:
    from src.modules.media.application.ports import (
        CatalogRequestLookupPort,
        CatalogRequestStatus,
        CollectionPartMetadata,
        MetadataProvider,
    )
    from src.modules.media.application.ports.profile_library_access_port import (
        ProfileLibraryAccessPort,
    )
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.entities.movie import Movie


class GetCollectionByTmdbIdUseCase:
    """Build the Collection Detail response for a TMDB collection id.

    The page lists every part of a TMDB franchise — including parts
    the platform doesn't host yet — so the use case fans out across
    three sources:

    1. **TMDB** — the franchise itself plus every member title's
       basic metadata (poster, year, rating, synopsis).
    2. **Local catalog** — for member titles that are already hosted,
       merge the local ``mov_xxx`` id and any locally-overriden
       artwork so the FilmRow can deep-link to Movie Detail and
       render the higher-quality local poster when available.
    3. **Catalog Requests** — for missing parts, surface the
       per-title request status so the FilmRow knows which CTA to
       show (Solicitar inclusão / Pedido registrado / Avisar
       quando chegar).

    Sort order is **release year ascending** with unknown years
    pushed to the end (TMDB's original order preserved among them).
    Chronological / diegetic ordering is intentionally omitted —
    TMDB doesn't expose it and faking it locally would lie to the
    user.

    A 404 from TMDB raises :class:`ResourceNotFoundException` so
    the route returns a typed 404. Network errors / malformed
    payloads also raise the same exception — the page expects an
    explicit failure rather than a hollow shell.

    Example:
        >>> uc = GetCollectionByTmdbIdUseCase(uow_factory, tmdb_client, catalog_request_lookup)
        >>> result = await uc.execute(GetCollectionByTmdbIdInput(tmdb_id=8091))
        >>> result.name
        'Alien Collection'
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        metadata_provider: MetadataProvider,
        catalog_request_lookup: CatalogRequestLookupPort,
        profile_library_access: ProfileLibraryAccessPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media UoW.
            metadata_provider: TMDB (or compatible) metadata client.
            catalog_request_lookup: Cross-BC port for resolving
                per-title request/notification status.
            profile_library_access: Port that resolves the caller's
                allowed library_ids. The TMDB call itself is unaffected
                — only the local-catalog overlay (which titles render
                with ``in_catalog=True``) is restricted.
        """
        self._uow_factory = uow_factory
        self._metadata = metadata_provider
        self._catalog_request_lookup = catalog_request_lookup
        self._profile_library_access = profile_library_access

    async def execute(
        self,
        input_dto: GetCollectionByTmdbIdInput,
    ) -> CollectionDetailOutput:
        """Run the lookup.

        A deny-all profile still hits TMDB (the page is informational
        about the franchise as a whole) but skips the local-catalog
        overlay so every part renders as missing.
        """
        collection = await self._metadata.get_collection(
            input_dto.tmdb_id,
            language=_to_bcp47(input_dto.lang),
        )
        if collection is None:
            raise ResourceNotFoundException.for_resource(
                "Collection",
                str(input_dto.tmdb_id),
            )

        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)

        # Cross-reference local catalog by TMDB id so we can stitch
        # the local mov_xxx + duration + artwork onto each TMDB part.
        part_tmdb_ids = [p.tmdb_id for p in collection.parts]
        local_movies: dict[int, Movie] = {}
        if allowed:
            async with self._uow_factory() as uow:
                local_movies = await uow.movies.find_by_tmdb_ids(
                    part_tmdb_ids, allowed_library_ids=allowed
                )

        # Per-title catalog-request status. Missing keys mean "no
        # request / no subscription" — the merge step defaults to
        # those, so the lookup stays additive.
        request_status = await self._catalog_request_lookup.get_for_movie_tmdb_ids(
            part_tmdb_ids,
        )

        merged: list[CollectionPartOutput] = [
            self._merge_part(
                part,
                local_movies.get(part.tmdb_id),
                request_status.get(part.tmdb_id),
                input_dto.lang,
            )
            for part in collection.parts
        ]

        # Release-year ASC with unknown years pushed to the back.
        # The original TMDB order is preserved among the unknown
        # tail thanks to the stable sort.
        ordered = sorted(
            merged,
            key=lambda p: (p.year is None, p.year or 0),
        )

        available = sum(1 for p in ordered if p.in_catalog)

        return CollectionDetailOutput(
            tmdb_id=collection.tmdb_id,
            name=collection.name,
            overview=collection.overview,
            poster_url=collection.poster_url,
            backdrop_url=collection.backdrop_url,
            total_parts=len(ordered),
            available_parts=available,
            missing_parts=len(ordered) - available,
            parts=ordered,
        )

    @staticmethod
    def _merge_part(
        tmdb_part: CollectionPartMetadata,
        local: Movie | None,
        request_status: CatalogRequestStatus | None,
        lang: str,
    ) -> CollectionPartOutput:
        """Stitch TMDB metadata, local catalog, and request status."""
        in_catalog = local is not None
        movie_id: str | None = None
        local_poster: str | None = None
        local_backdrop: str | None = None
        runtime_seconds: int | None = None
        runtime_formatted: str | None = None
        title = tmdb_part.title
        synopsis = tmdb_part.synopsis
        year = tmdb_part.year

        if local is not None:
            movie_id = str(local.id)
            local_poster = local.get_poster_path(lang)
            local_backdrop = local.get_backdrop_path(lang)
            runtime_seconds = local.duration.value
            runtime_formatted = local.duration.format_hms()
            # Prefer locally-managed (often translated) fields when
            # present so the UI is consistent with Movie Detail.
            title = local.get_title(lang) or title
            synopsis = local.get_synopsis(lang) or synopsis
            year = local.year.value or year
        elif tmdb_part.year is not None:
            # Without a local row TMDB only carries best-effort
            # data; runtime stays empty (we haven't fetched per-part
            # details, that would explode the round-trip count).
            runtime_seconds = None

        # ``request_status`` is the cross-BC lookup result; it's
        # only present when the user has registered something.
        is_requested = request_status.is_requested if request_status is not None else False
        notify_on_arrival = (
            request_status.notify_on_arrival if request_status is not None else False
        )

        # Available parts shouldn't render the request CTA — collapse
        # the flags to ``False`` so the UI doesn't need a special case.
        if in_catalog:
            is_requested = False
            notify_on_arrival = False

        return CollectionPartOutput(
            tmdb_id=tmdb_part.tmdb_id,
            title=title,
            year=year,
            synopsis=synopsis,
            poster_url=tmdb_part.poster_url,
            backdrop_url=tmdb_part.backdrop_url,
            rating=tmdb_part.rating,
            runtime_seconds=runtime_seconds,
            runtime_formatted=runtime_formatted,
            in_catalog=in_catalog,
            movie_id=movie_id,
            local_poster_path=local_poster or tmdb_part.poster_url,
            local_backdrop_path=local_backdrop or tmdb_part.backdrop_url,
            is_requested=is_requested,
            notify_on_arrival=notify_on_arrival,
        )


def _to_bcp47(lang: str) -> str:
    """Map our short language codes to TMDB's BCP-47 tags.

    The frontend speaks ``"en"`` / ``"pt-BR"`` and TMDB wants
    ``"en-US"`` / ``"pt-BR"``. Anything that already looks like a
    BCP-47 tag (contains a hyphen) is forwarded as-is.
    """
    if "-" in lang:
        return lang
    if lang.lower() == "en":
        return "en-US"
    return lang


__all__ = ["GetCollectionByTmdbIdUseCase"]
