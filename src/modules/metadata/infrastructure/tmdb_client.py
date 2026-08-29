"""TMDB API client implementing MetadataProvider port."""

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Literal, cast

import httpx

from src.building_blocks.infrastructure.errors import (
    GatewayBadResponseException,
    GatewayException,
    GatewayRateLimitException,
    GatewayTimeoutException,
    GatewayUnavailableException,
)
from src.modules.metadata.application.ports.metadata_provider_port import (
    CollectionDetailMetadata,
    CollectionMetadata,
    LocalizedFields,
    MediaMetadata,
    MetadataProvider,
    PersonMetadata,
    SearchCandidate,
    SeasonMetadata,
)
from src.modules.metadata.infrastructure.tmdb_response_mapper import TmdbResponseMapper
from src.shared_kernel.value_objects import MediaType

_GATEWAY_NAME = "TMDB"


def _parse_retry_after(value: str | None) -> int | None:
    """Parse a ``Retry-After`` header (delta-seconds) into an int.

    TMDB sends the delay as an integer number of seconds. Returns
    ``None`` when the header is absent or not a plain integer so the
    caller can fall back to the exception's default — the HTTP-date
    form of ``Retry-After`` is not emitted by TMDB and is treated as
    "unknown" rather than parsed.
    """
    if value is None:
        return None
    try:
        seconds = int(value.strip())
    except (ValueError, AttributeError):
        return None
    return seconds if seconds >= 0 else None


def _is_english(language: str) -> bool:
    """Return ``True`` for any English BCP-47 tag (``en``, ``en-US``, ``en-GB``).

    Used by ``get_person`` to decide whether the requested-language
    fetch already gave us the English bio (no fallback needed).
    """
    return language.lower().split("-", 1)[0] == "en"


class TmdbClient(MetadataProvider):
    """The Movie Database (TMDB) API client.

    Thin HTTP orchestrator: it owns auth/params, the GET round-trip,
    retry/rate-limit/error translation, and JSON parsing, then delegates
    every payload → DTO shaping to :class:`TmdbResponseMapper`.

    Localized enrichment always fetches English as the base metadata,
    then overlays one translation per configured non-English locale
    (``supported_locales`` from ``Settings``). Each overlay is stored
    under its BCP-47 tag in ``MediaMetadata.localized``, so adding a
    language is a config change — no code edit. A locale whose
    translation fetch fails is skipped; the others still apply.

    Args:
        api_key: TMDB API key (v3 auth).
        base_url: TMDB API base URL.
        supported_locales: BCP-47 tags the catalog serves (e.g.
            ``("en", "pt-BR")``). English is the base and is dropped
            from the overlay set, so only the remaining locales drive
            extra translation fetches. Defaults to ``("en", "pt-BR")``
            to preserve the legacy English + pt-BR behavior when the
            client is constructed without explicit config.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.themoviedb.org/3",
        supported_locales: Sequence[str] = ("en", "pt-BR"),
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)
        self._supported_locales = list(supported_locales)
        # English is the base metadata, so it never appears as an
        # overlay. Everything else becomes one extra details fetch.
        self._localized_locales = [
            locale for locale in supported_locales if not _is_english(locale)
        ]
        self._mapper = TmdbResponseMapper(supported_locales=tuple(supported_locales))

    def _params(self, **extra: str | int | None) -> dict[str, str | int]:
        params: dict[str, str | int] = {"api_key": self._api_key}
        for k, v in extra.items():
            if v is not None:
                params[k] = v
        return params

    def _image_url(self, path: str | None) -> str | None:
        return self._mapper.image_url(path)

    async def _get(
        self,
        path: str,
        params: dict[str, str | int],
    ) -> httpx.Response:
        """Perform a GET against TMDB, translating transport failures.

        Wraps httpx transport-level errors (timeouts, connection / DNS
        failures) into the matching :class:`GatewayException` subtype so
        this ACL never leaks a raw ``httpx`` error past the boundary —
        the global handler can then surface ``503`` / ``504`` instead of
        a generic ``500`` ("the provider is down" is not "our server
        crashed").

        HTTP *status* errors are deliberately NOT raised here: the
        response is returned as-is so a caller can inspect the status
        (e.g. tell a genuine ``404`` apart from a provider outage) before
        deciding whether to call :meth:`_raise_for_status`.

        Args:
            path: Request path relative to the API base (e.g.
                ``"/movie/123"``).
            params: Query parameters, already including the api key.

        Returns:
            The raw ``httpx.Response``, regardless of status code.

        Raises:
            GatewayTimeoutException: The request timed out.
            GatewayUnavailableException: TMDB could not be reached
                (connection refused, DNS failure, protocol error).
        """
        try:
            return await self._client.get(f"{self._base_url}{path}", params=params)
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutException(
                message="TMDB request timed out",
                gateway_name=_GATEWAY_NAME,
                internal_message=f"{type(exc).__name__}: {exc}",
            ) from exc
        except httpx.HTTPError as exc:
            raise GatewayUnavailableException(
                message="TMDB is unavailable",
                gateway_name=_GATEWAY_NAME,
                internal_message=f"{type(exc).__name__}: {exc}",
            ) from exc

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        """Translate a non-2xx TMDB response into a ``GatewayException``.

        Maps the provider's HTTP status onto the gateway subtype whose
        ``code`` the registry resolves to the right client-facing status
        (``429`` / ``502`` / ``503`` / ``504``), so a provider problem is
        never reported to the caller as a generic ``500``. A ``4xx`` other
        than rate-limiting means *our* request or credentials were at
        fault (it is not a provider outage), so it maps to the base
        ``GatewayException`` (``500``). Callers that treat a ``404``
        specially must check ``resp.status_code`` before calling this.

        Raises:
            GatewayRateLimitException: HTTP 429.
            GatewayTimeoutException: HTTP 504.
            GatewayUnavailableException: HTTP 503 or any other 5xx.
            GatewayBadResponseException: HTTP 502.
            GatewayException: Any other non-2xx (4xx) response.
        """
        status = resp.status_code
        if status < httpx.codes.BAD_REQUEST:
            return

        internal = f"HTTP {status} from {resp.request.url}"

        if status == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            raise GatewayRateLimitException(
                message="TMDB rate limit exceeded",
                gateway_name=_GATEWAY_NAME,
                retry_after_seconds=retry_after if retry_after is not None else 60,
                internal_message=internal,
            )
        if status == httpx.codes.GATEWAY_TIMEOUT:
            raise GatewayTimeoutException(
                message="TMDB timed out upstream",
                gateway_name=_GATEWAY_NAME,
                internal_message=internal,
            )
        if status == httpx.codes.BAD_GATEWAY:
            raise GatewayBadResponseException(
                message="TMDB returned a bad-gateway response",
                gateway_name=_GATEWAY_NAME,
                internal_message=internal,
            )
        if status >= httpx.codes.INTERNAL_SERVER_ERROR:
            # 503 and every other 5xx — the provider is having problems.
            raise GatewayUnavailableException(
                message="TMDB is unavailable",
                gateway_name=_GATEWAY_NAME,
                internal_message=internal,
            )
        raise GatewayException(
            message="TMDB request failed",
            gateway_name=_GATEWAY_NAME,
            internal_message=internal,
        )

    @staticmethod
    def _json(resp: httpx.Response) -> Any:
        """Parse a TMDB response body as JSON, wrapping malformed payloads.

        TMDB occasionally returns a non-JSON body — an HTML error page,
        a truncated/empty payload — alongside a ``2xx`` status.
        ``httpx.Response.json`` raises ``ValueError``
        (``json.JSONDecodeError``) for those, which would otherwise leak
        past this ACL and surface as a generic ``500``. Translating it to
        :class:`GatewayBadResponseException` lets the global handler report
        ``502`` ("the provider sent us garbage", not "our server crashed")
        and lets best-effort callers that already catch ``GatewayException``
        degrade gracefully — the same way they treat a wrapped transport
        failure.

        Raises:
            GatewayBadResponseException: The response body is not valid JSON.
        """
        try:
            return resp.json()
        except ValueError as exc:
            raise GatewayBadResponseException(
                message="TMDB returned a malformed response",
                gateway_name=_GATEWAY_NAME,
                internal_message=f"{type(exc).__name__}: {exc}",
            ) from exc

    async def search_movie(self, title: str, year: int | None = None) -> MediaMetadata | None:
        """Search TMDB for a movie and return metadata for the best match.

        When ``year`` is provided, results are filtered to entries whose
        ``release_date`` falls in that exact year — TMDB's ``year`` query
        param is a soft ranking signal, not a hard filter, so without
        this post-filter a popular off-year title (e.g. ``Salem's Lot``
        2024) can outrank the year-correct entry. Returns ``None`` when
        no result matches the requested year; the caller's retry layer
        will re-search without the year hint.
        """
        resp = await self._get(
            "/search/movie",
            params=self._params(query=title, year=year),
        )
        self._raise_for_status(resp)
        results = self._json(resp).get("results", [])

        best = self._mapper.pick_year_match(results, year, "release_date")
        if best is None:
            return None

        return await self._fetch_movie_details(cast(int, best["id"]))

    async def search_series(self, title: str, year: int | None = None) -> MediaMetadata | None:
        """Search TMDB for a TV series and return metadata for the best match.

        When ``year`` is provided, results are filtered to entries whose
        ``first_air_date`` falls in that exact year. See ``search_movie``
        for the rationale: ``first_air_date_year`` boosts ranking but does
        not strictly filter, so the more-popular off-year entry can come
        back first (e.g. ``American Gothic`` 1995 outranking the 2016
        revival). Returns ``None`` when no result matches the requested
        year.
        """
        resp = await self._get(
            "/search/tv",
            params=self._params(query=title, first_air_date_year=year),
        )
        self._raise_for_status(resp)
        results = self._json(resp).get("results", [])

        best = self._mapper.pick_year_match(results, year, "first_air_date")
        if best is None:
            return None

        return await self._fetch_series_details(cast(int, best["id"]))

    async def find_movie_candidates(
        self,
        title: str,
        year: int | None = None,
        limit: int = 5,
    ) -> list[SearchCandidate]:
        """Return the top ``limit`` raw movie search hits.

        See ``find_movie_candidates`` on ``MetadataProvider`` for the
        contract — picker-mode, no year post-filter, TMDB's own
        popularity ranking preserved.
        """
        resp = await self._get(
            "/search/movie",
            params=self._params(query=title, year=year),
        )
        self._raise_for_status(resp)
        results = self._json(resp).get("results", [])
        return [self._mapper.movie_candidate(r) for r in results[:limit]]

    async def find_series_candidates(
        self,
        title: str,
        year: int | None = None,
        limit: int = 5,
    ) -> list[SearchCandidate]:
        """Return the top ``limit`` raw TV search hits."""
        resp = await self._get(
            "/search/tv",
            params=self._params(query=title, first_air_date_year=year),
        )
        self._raise_for_status(resp)
        results = self._json(resp).get("results", [])
        return [self._mapper.series_candidate(r) for r in results[:limit]]

    async def get_movie_summary_by_id(self, tmdb_id: int) -> SearchCandidate | None:
        """Cheap ``/movie/{id}`` fetch shaped as a picker candidate.

        A genuine 404 (the id is not a movie) returns ``None``; any other
        failure (network, auth, rate limit, 5xx) propagates via
        ``raise_for_status`` — consistent with the search paths — so a
        transient outage doesn't masquerade as "not found".
        """
        resp = await self._get(
            f"/movie/{tmdb_id}",
            params=self._params(),
        )
        if resp.status_code == httpx.codes.NOT_FOUND:
            return None
        self._raise_for_status(resp)
        return self._mapper.movie_candidate(self._json(resp))

    async def get_series_summary_by_id(self, tmdb_id: int) -> SearchCandidate | None:
        """Cheap ``/tv/{id}`` fetch shaped as a picker candidate.

        404 (the id is not a series) returns ``None``; any other failure
        propagates via ``raise_for_status`` instead of collapsing to
        not-found.
        """
        resp = await self._get(
            f"/tv/{tmdb_id}",
            params=self._params(),
        )
        if resp.status_code == httpx.codes.NOT_FOUND:
            return None
        self._raise_for_status(resp)
        return self._mapper.series_candidate(self._json(resp))

    async def find_by_imdb_id(self, imdb_id: str) -> list[SearchCandidate]:
        """Resolve an IMDb id via ``/find`` and return movie + TV hits.

        The response carries separate ``movie_results`` and
        ``tv_results`` arrays — same IMDb id can match both shapes
        (rare, but happens for adaptations). Movies come first to
        match the conventional "film over series" expectation when the
        user pastes ``tt`` from a movie page; tests can stable-sort
        on ``media_type`` afterwards if they need a stricter order.
        """
        resp = await self._get(
            f"/find/{imdb_id}",
            params=self._params(external_source="imdb_id"),
        )
        self._raise_for_status(resp)
        payload = self._json(resp)
        movies = [self._mapper.movie_candidate(r) for r in payload.get("movie_results", [])]
        series = [self._mapper.series_candidate(r) for r in payload.get("tv_results", [])]
        return [*movies, *series]

    async def get_movie_by_id(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch movie details by TMDB ID."""
        return await self._fetch_movie_details(tmdb_id)

    async def get_movie_localized(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch movie details in English with per-locale localization.

        English is the base metadata; one translation is overlaid per
        configured non-English locale (``supported_locales``). Each
        localized details call appends ``images`` filtered to that
        locale / en / language-neutral, so the localized logo comes
        back in the same round-trip. ``Movie.get_logo_path(lang)``
        picks the localized one when present and falls back to the
        global (en) otherwise — same shape as title/synopsis. A locale
        whose fetch fails is skipped; the English base is still
        returned.
        """
        en_meta = await self._fetch_movie_details(tmdb_id, language="en-US")
        if not en_meta:
            return None

        localized: dict[str, LocalizedFields] = {}
        for locale in self._localized_locales:
            fields = await self._fetch_movie_localized_fields(tmdb_id, locale)
            if fields is not None:
                localized[locale] = fields

        return replace(en_meta, localized=localized)

    async def _fetch_movie_localized_fields(
        self, tmdb_id: int, locale: str
    ) -> LocalizedFields | None:
        """Fetch one locale's translated movie fields, or ``None`` on failure.

        An overlay is best-effort: any provider failure (non-200 status
        or a wrapped transport ``GatewayException``) drops just this
        locale so the English base still returns.
        """
        try:
            resp = await self._get(
                f"/movie/{tmdb_id}",
                params=self._params(
                    language=locale,
                    append_to_response="images",
                    include_image_language=f"{locale},en,null",
                ),
            )
            if resp.status_code != 200:
                return None
            data = self._json(resp)
        except GatewayException:
            return None

        return self._mapper.shape_localized_movie_fields(data, locale)

    async def get_series_by_id(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch series details by TMDB ID."""
        return await self._fetch_series_details(tmdb_id)

    async def get_collection(
        self,
        tmdb_id: int,
        language: str = "en-US",
    ) -> CollectionDetailMetadata | None:
        """Fetch ``/collection/{id}`` and shape it for the Collection Detail UI.

        TMDB returns the collection-level fields (``name``,
        ``overview``, ``poster_path``, ``backdrop_path``) plus a
        ``parts`` array — one entry per member title. Shaping is
        delegated to :meth:`TmdbResponseMapper.shape_collection_detail`.

        404 / network errors / non-dict payloads degrade to ``None``
        so the use case can render an "unavailable" state rather
        than 500.
        """
        try:
            resp = await self._get(
                f"/collection/{tmdb_id}",
                params=self._params(language=language),
            )
            if resp.status_code != 200:
                return None
            data = self._json(resp)
        except GatewayException:
            return None
        if not isinstance(data, dict):
            return None

        return self._mapper.shape_collection_detail(data)

    async def get_movie_recommendations(self, tmdb_id: int) -> list[int]:
        """Return TMDB ids of movies related to ``tmdb_id``.

        Three sources are merged, in descending relevance:

        1. **Collection siblings** — when the movie belongs to a TMDB
           collection (franchises, e.g. "Creepshow Collection"), every
           other entry in the collection. Sequels / prequels are the
           most obvious "related" signal but TMDB's ML doesn't always
           expose them, especially for older or less popular titles.
        2. **``/recommendations``** — ML-based.
        3. **``/similar``** — heuristic fallback (genre / keyword
           overlap), only used when recommendations is empty.

        Sources 1 + 2 (or 1 + 3) are merged in order, with the input
        movie itself skipped and duplicates removed so the same id
        never appears twice.

        Network failures and unexpected payload shapes degrade to an
        empty list — recommendation rendering is best-effort polish,
        never load-bearing.
        """
        collection_ids = await self._fetch_collection_movie_ids(tmdb_id)
        other_ids = await self._fetch_related_ids(tmdb_id, "movie", "recommendations")
        if not other_ids:
            other_ids = await self._fetch_related_ids(tmdb_id, "movie", "similar")

        seen: set[int] = {tmdb_id}
        ordered: list[int] = []
        for tid in [*collection_ids, *other_ids]:
            if tid in seen:
                continue
            seen.add(tid)
            ordered.append(tid)
        return ordered

    async def get_series_recommendations(self, tmdb_id: int) -> list[int]:
        """Return TMDB ids of series related to ``tmdb_id``.

        Series have no collection equivalent on TMDB (no ``parts``
        list akin to movie franchises), so the source list is just:

        1. **``/recommendations``** — ML-based.
        2. **``/similar``** — heuristic fallback, only used when
           recommendations is empty.

        Network failures and unexpected payload shapes degrade to an
        empty list — recommendation rendering is best-effort polish,
        never load-bearing.
        """
        ids = await self._fetch_related_ids(tmdb_id, "tv", "recommendations")
        if not ids:
            ids = await self._fetch_related_ids(tmdb_id, "tv", "similar")

        seen: set[int] = {tmdb_id}
        ordered: list[int] = []
        for tid in ids:
            if tid in seen:
                continue
            seen.add(tid)
            ordered.append(tid)
        return ordered

    async def _fetch_collection_movie_ids(self, tmdb_id: int) -> list[int]:  # noqa: PLR0911
        """Return ids of every movie in the input movie's TMDB collection.

        Two-call shape: first ``/movie/{id}`` (minimal, just to read
        ``belongs_to_collection``), then ``/collection/{coll_id}`` for
        the ``parts`` list. Both are cheap on the TMDB side and only
        run for the recommendations endpoint, so the extra round-trip
        is fine.

        Returns an empty list when the movie has no collection or any
        step fails — collection lookup is best-effort polish.
        """
        try:
            resp = await self._get(
                f"/movie/{tmdb_id}",
                params=self._params(),
            )
            if resp.status_code != 200:
                return []
            coll = self._json(resp).get("belongs_to_collection")
        except GatewayException:
            return []
        if not isinstance(coll, dict):
            return []
        coll_id = coll.get("id")
        if not isinstance(coll_id, int):
            return []

        try:
            resp = await self._get(
                f"/collection/{coll_id}",
                params=self._params(),
            )
            if resp.status_code != 200:
                return []
            parts = self._json(resp).get("parts") or []
        except GatewayException:
            return []
        ids: list[int] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            pid = part.get("id")
            if isinstance(pid, int):
                ids.append(pid)
        return ids

    async def _fetch_related_ids(
        self,
        tmdb_id: int,
        media_type: Literal["movie", "tv"],
        endpoint: Literal["recommendations", "similar"],
    ) -> list[int]:
        """Hit a single ``/{media_type}/{id}/<endpoint>`` and extract numeric ids.

        ``media_type`` is ``"movie"`` or ``"tv"``; ``endpoint`` is
        ``"recommendations"`` or ``"similar"``. Both endpoints paginate
        but page 1 already carries enough candidates for the UI's
        ~10-item carousel and a second request would just burn latency
        on results we'd discard.
        """
        try:
            resp = await self._get(
                f"/{media_type}/{tmdb_id}/{endpoint}",
                params=self._params(),
            )
            if resp.status_code != 200:
                return []
            results = self._json(resp).get("results") or []
        except GatewayException:
            return []
        ids: list[int] = []
        for item in results:
            raw = item.get("id") if isinstance(item, dict) else None
            if isinstance(raw, int):
                ids.append(raw)
        return ids

    async def get_person(
        self,
        tmdb_id: int,
        language: str = "en-US",
    ) -> PersonMetadata | None:
        """Fetch biographical metadata for a person from TMDB.

        Hits ``/person/{id}?language=<lang>`` and falls back to
        ``en-US`` for the biography text alone when TMDB returns a
        blank one in the requested language. The fallback is
        bio-only because TMDB authors translations field-by-field —
        a missing Portuguese ``biography`` doesn't mean ``birthday``
        / ``place_of_birth`` are also missing in pt-BR (they often
        aren't), so blowing the whole payload away would lose
        translations the user actually has.

        Network failures and unexpected payloads degrade to ``None``
        so the actor page falls back to a name-only header instead
        of erroring out.
        """
        meta = await self._fetch_person(tmdb_id, language)
        if meta is None or meta.biography or _is_english(language):
            return meta
        # Bio came back empty in a non-English locale — try English
        # so the panel isn't blank when TMDB only authored the bio
        # for one language.
        en_meta = await self._fetch_person(tmdb_id, "en-US")
        if en_meta is None or not en_meta.biography:
            return meta

        return replace(meta, biography=en_meta.biography)

    async def _fetch_person(self, tmdb_id: int, language: str) -> PersonMetadata | None:
        """Single ``/person/{id}`` round-trip in ``language``."""
        try:
            resp = await self._get(
                f"/person/{tmdb_id}",
                params=self._params(language=language),
            )
            if resp.status_code != 200:
                return None
            data = self._json(resp)
        except GatewayException:
            return None
        return self._mapper.shape_person(data)

    async def get_series_localized(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch series details in English with per-locale localization.

        Same per-locale strategy as ``get_movie_localized``: English is
        the base and one translation is overlaid per configured
        non-English locale (``supported_locales``). Each localized
        details call appends ``images`` so the localized logo comes
        back without an extra HTTP fetch.
        """
        en_meta = await self._fetch_series_details(tmdb_id)
        if not en_meta:
            return None

        localized: dict[str, LocalizedFields] = {}
        for locale in self._localized_locales:
            fields = await self._fetch_series_localized_fields(tmdb_id, locale)
            if fields is not None:
                localized[locale] = fields

        return replace(en_meta, localized=localized)

    async def get_translated_titles(self, tmdb_id: int, media_type: MediaType) -> dict[str, str]:
        """Resolve per-locale titles for the configured supported locales.

        One ``/translations`` round-trip; maps each supported BCP-47 tag
        to its TMDB-translated title (e.g. ``{"en": ..., "pt-BR": ...}``).
        Locales with no translation are omitted. Best-effort: returns
        ``{}`` on any HTTP/parse failure so callers fall back to their
        own snapshot.
        """
        path = "movie" if media_type == MediaType.MOVIE else "tv"
        title_key = "title" if media_type == MediaType.MOVIE else "name"
        try:
            resp = await self._get(
                f"/{path}/{tmdb_id}/translations",
                params=self._params(),
            )
            if resp.status_code != 200:
                return {}
            translations = self._json(resp).get("translations", [])
        except GatewayException:
            return {}
        return self._mapper.shape_translated_titles(translations, title_key)

    async def _fetch_series_localized_fields(
        self, tmdb_id: int, locale: str
    ) -> LocalizedFields | None:
        """Fetch one locale's translated series fields, or ``None`` on failure.

        An overlay is best-effort: any provider failure (non-200 status
        or a wrapped transport ``GatewayException``) drops just this
        locale so the English base still returns.
        """
        try:
            resp = await self._get(
                f"/tv/{tmdb_id}",
                params=self._params(
                    language=locale,
                    append_to_response="images",
                    include_image_language=f"{locale},en,null",
                ),
            )
            if resp.status_code != 200:
                return None
            data = self._json(resp)
        except GatewayException:
            return None

        return self._mapper.shape_localized_series_fields(data, locale)

    async def _fetch_movie_details(
        self, tmdb_id: int, language: str = "en-US"
    ) -> MediaMetadata | None:
        """Fetch full movie details from TMDB.

        ``images`` is appended to the response (with
        ``include_image_language`` filtered to the requested language,
        English, and language-neutral) so the title logo comes back
        in the same round-trip — saves a separate HTTP call per
        details fetch. The ``belongs_to_collection`` follow-up fetch is
        resolved here and handed to the mapper for shaping.
        """
        resp = await self._get(
            f"/movie/{tmdb_id}",
            params=self._params(
                append_to_response="credits,release_dates,videos,images",
                language=language,
                include_image_language=f"{language},en,null",
            ),
        )
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)
        data = self._json(resp)

        collection = await self._fetch_collection_metadata(data.get("belongs_to_collection"))
        return self._mapper.shape_movie_metadata(data, language, collection)

    async def _fetch_collection_metadata(
        self,
        belongs_to: dict[str, object] | None,
    ) -> CollectionMetadata | None:
        """Build a ``CollectionMetadata`` from the ``belongs_to_collection`` payload.

        Hits ``/collection/{id}`` once for ``parts_count``. Best-effort polish
        — any HTTP/parse error degrades to ``None`` so a flaky collection
        lookup never breaks movie enrichment.
        """
        if not isinstance(belongs_to, dict):
            return None
        coll_id = belongs_to.get("id")
        name = belongs_to.get("name")
        if not isinstance(coll_id, int) or not isinstance(name, str):
            return None

        try:
            resp = await self._get(
                f"/collection/{coll_id}",
                params=self._params(),
            )
            if resp.status_code != 200:
                return None
            parts = self._json(resp).get("parts") or []
        except GatewayException:
            return None
        return CollectionMetadata(tmdb_id=coll_id, name=name, parts_count=len(parts))

    async def _fetch_series_details(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch full series details including seasons and episodes.

        Same trick as ``_fetch_movie_details``: ``images`` is appended
        so the title logo comes back in this round-trip; default
        language is English since the bulk of the series-details flow
        is English-first (the localized variant overrides on top). The
        per-season episode fetches are resolved here and handed to the
        mapper for shaping.
        """
        resp = await self._get(
            f"/tv/{tmdb_id}",
            params=self._params(
                append_to_response="external_ids,content_ratings,videos,images,credits",
                include_image_language="en,null",
            ),
        )
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)
        data = self._json(resp)

        # Fetch season details with episodes
        seasons: list[SeasonMetadata] = []
        for s in data.get("seasons", []):
            season_num = s.get("season_number", 0)
            season_meta = await self._fetch_season(tmdb_id, season_num)
            if season_meta:
                seasons.append(season_meta)

        return self._mapper.shape_series_metadata(data, seasons)

    async def _fetch_season(self, series_id: int, season_number: int) -> SeasonMetadata | None:
        """Fetch season details + episodes with per-locale title/synopsis overlays.

        The English payload is the base; each configured non-English
        locale is fetched **concurrently** (one ``/season/{n}?language=``
        round-trip per locale) and folded into per-season and
        per-episode ``localized`` overrides keyed by BCP-47 tag. A
        locale fetch that fails is skipped — the English base still
        returns. Seasons themselves are fetched sequentially by the
        caller; only this locale fan-out is concurrent. The shaping is
        delegated to :meth:`TmdbResponseMapper.shape_season`.
        """
        languages: list[str | None] = [None, *self._localized_locales]
        payloads = await asyncio.gather(
            *(self._fetch_season_payload(series_id, season_number, lang) for lang in languages)
        )

        base = payloads[0]
        if base is None:
            return None

        # locale -> payload, dropping any overlay that failed to load.
        loc_payloads: dict[str, dict[str, Any]] = {
            locale: payload
            for locale, payload in zip(self._localized_locales, payloads[1:], strict=True)
            if payload is not None
        }

        return self._mapper.shape_season(season_number, base, loc_payloads)

    async def _fetch_season_payload(
        self, series_id: int, season_number: int, language: str | None
    ) -> dict[str, Any] | None:
        """One ``/season/{n}`` round-trip; ``None`` on 404 or locale-overlay failure.

        ``language=None`` is the English base — a non-404 error there
        is fatal (raised). For a localized overlay any failure (non-200
        status or a wrapped transport ``GatewayException``) simply drops
        that locale, so a flaky overlay never aborts the concurrent
        season fan-out.
        """
        try:
            resp = await self._get(
                f"/tv/{series_id}/season/{season_number}",
                params=self._params(language=language),
            )
            if resp.status_code == 404:
                return None
            if language is not None and resp.status_code != 200:
                return None
            if language is None:
                self._raise_for_status(resp)
            data: dict[str, Any] = self._json(resp)
        except GatewayException:
            if language is None:
                raise
            return None
        return data


__all__ = ["TmdbClient"]
