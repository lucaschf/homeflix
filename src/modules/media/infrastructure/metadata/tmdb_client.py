"""TMDB API client implementing MetadataProvider port."""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any, Literal

import httpx

from src.modules.media.application.ports import (
    CollectionDetailMetadata,
    CollectionMetadata,
    CollectionPartMetadata,
    CreditPerson,
    EpisodeMetadata,
    LocalizedFields,
    LocalizedTextFields,
    MediaMetadata,
    MetadataProvider,
    PersonMetadata,
    SearchCandidate,
    SeasonMetadata,
)
from src.modules.media.domain.value_objects import ContentRating
from src.shared_kernel.value_objects import MediaType

_MAX_CAST = 15


def _safe_int(value: object, default: int) -> int:
    """Safely convert a value to int, returning default on failure."""
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return default


_TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"


def _is_english(language: str) -> bool:
    """Return ``True`` for any English BCP-47 tag (``en``, ``en-US``, ``en-GB``).

    Used by ``get_person`` to decide whether the requested-language
    fetch already gave us the English bio (no fallback needed).
    """
    return language.lower().split("-", 1)[0] == "en"


def _episode_payload_by_number(
    season_payload: dict[str, Any], episode_number: int
) -> dict[str, Any] | None:
    """Find an episode dict in a season payload by its ``episode_number``."""
    episodes: list[dict[str, Any]] = season_payload.get("episodes", [])
    for ep in episodes:
        if ep.get("episode_number") == episode_number:
            return ep
    return None


def _pick_translation_title(
    translations: list[dict[str, Any]], locale: str, title_key: str
) -> str | None:
    """Pick a title from a TMDB ``/translations`` payload for a BCP-47 locale.

    Prefers an exact language+region match (``pt`` + ``BR`` for
    ``pt-BR``), then falls back to the first entry sharing the base
    language. Returns ``None`` when the locale has no usable title.
    """
    parts = locale.split("-", 1)
    lang = parts[0].lower()
    region = parts[1].upper() if len(parts) > 1 else None

    base: str | None = None
    for tr in translations:
        if not isinstance(tr, dict):
            continue
        if str(tr.get("iso_639_1", "")).lower() != lang:
            continue
        title = (tr.get("data") or {}).get(title_key)
        if not isinstance(title, str) or not title:
            continue
        if region and str(tr.get("iso_3166_1", "")).upper() == region:
            return title
        if base is None:
            base = title
    return base


class TmdbClient(MetadataProvider):
    """The Movie Database (TMDB) API client.

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

    def _params(self, **extra: str | int | None) -> dict[str, str | int]:
        params: dict[str, str | int] = {"api_key": self._api_key}
        for k, v in extra.items():
            if v is not None:
                params[k] = v
        return params

    def _image_url(self, path: str | None) -> str | None:
        return f"{_TMDB_IMAGE_BASE}{path}" if path else None

    @staticmethod
    def _logo_rank(logo: dict[str, object], target: str, target_base: str) -> int:
        """Score a TMDB logo entry for language preference (lower = better).

        Priority:
            0. exact language match (``pt-BR`` for a pt-BR request)
            1. base language match (``pt`` covers ``pt-BR`` / ``pt-PT``)
            2. English (``en``)
            3. language-neutral (``iso_639_1 is None``)
            4. anything else — last-resort fallback
        """
        iso = logo.get("iso_639_1")
        if iso is None:
            return 3
        if not isinstance(iso, str):
            return 4
        iso_lower = iso.lower()
        if iso_lower == target:
            return 0
        if iso_lower.split("-", 1)[0] == target_base:
            return 1
        if iso_lower == "en":
            return 2
        return 4

    def _pick_best_logo_url(
        self,
        logos: list[dict[str, object]] | None,
        language: str,
    ) -> str | None:
        """Pick the best-language logo URL from a TMDB ``logos`` payload.

        Pure function — no HTTP. Caller already has the logo list from
        ``data["images"]["logos"]`` on a details response that included
        ``images`` in ``append_to_response``. Returns ``None`` when the
        list is empty / missing or the best entry has no ``file_path``.
        """
        if not logos:
            return None
        target = language.lower()
        target_base = target.split("-", 1)[0]
        best = min(logos, key=lambda logo: self._logo_rank(logo, target, target_base))
        return self._image_url(best.get("file_path"))

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
        resp = await self._client.get(
            f"{self._base_url}/search/movie",
            params=self._params(query=title, year=year),
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        best = self._pick_year_match(results, year, "release_date")
        if best is None:
            return None

        return await self._fetch_movie_details(best["id"])

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
        resp = await self._client.get(
            f"{self._base_url}/search/tv",
            params=self._params(query=title, first_air_date_year=year),
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        best = self._pick_year_match(results, year, "first_air_date")
        if best is None:
            return None

        return await self._fetch_series_details(best["id"])

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
        resp = await self._client.get(
            f"{self._base_url}/search/movie",
            params=self._params(query=title, year=year),
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [_to_movie_candidate(r, self._image_url) for r in results[:limit]]

    async def find_series_candidates(
        self,
        title: str,
        year: int | None = None,
        limit: int = 5,
    ) -> list[SearchCandidate]:
        """Return the top ``limit`` raw TV search hits."""
        resp = await self._client.get(
            f"{self._base_url}/search/tv",
            params=self._params(query=title, first_air_date_year=year),
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [_to_series_candidate(r, self._image_url) for r in results[:limit]]

    async def get_movie_summary_by_id(self, tmdb_id: int) -> SearchCandidate | None:
        """Cheap ``/movie/{id}`` fetch shaped as a picker candidate."""
        try:
            resp = await self._client.get(
                f"{self._base_url}/movie/{tmdb_id}",
                params=self._params(),
            )
        except httpx.HTTPError:
            return None
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        return _to_movie_candidate(resp.json(), self._image_url)

    async def get_series_summary_by_id(self, tmdb_id: int) -> SearchCandidate | None:
        """Cheap ``/tv/{id}`` fetch shaped as a picker candidate."""
        try:
            resp = await self._client.get(
                f"{self._base_url}/tv/{tmdb_id}",
                params=self._params(),
            )
        except httpx.HTTPError:
            return None
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        return _to_series_candidate(resp.json(), self._image_url)

    async def find_by_imdb_id(self, imdb_id: str) -> list[SearchCandidate]:
        """Resolve an IMDb id via ``/find`` and return movie + TV hits.

        The response carries separate ``movie_results`` and
        ``tv_results`` arrays — same IMDb id can match both shapes
        (rare, but happens for adaptations). Movies come first to
        match the conventional "film over series" expectation when the
        user pastes ``tt`` from a movie page; tests can stable-sort
        on ``media_type`` afterwards if they need a stricter order.
        """
        resp = await self._client.get(
            f"{self._base_url}/find/{imdb_id}",
            params=self._params(external_source="imdb_id"),
        )
        resp.raise_for_status()
        payload = resp.json()
        movies = [_to_movie_candidate(r, self._image_url) for r in payload.get("movie_results", [])]
        series = [_to_series_candidate(r, self._image_url) for r in payload.get("tv_results", [])]
        return [*movies, *series]

    @staticmethod
    def _pick_year_match(
        results: list[dict[str, object]],
        year: int | None,
        date_field: str,
    ) -> dict[str, object] | None:
        """Pick the first result whose ``date_field`` starts with ``year``.

        Without a ``year`` hint, falls back to the first result (TMDB's
        own popularity ranking). With a ``year`` hint, returns ``None``
        if no result matches — strict year semantics, to avoid silently
        returning a popular off-year entry.
        """
        if not results:
            return None
        if year is None:
            return results[0]

        prefix = f"{year}"
        for result in results:
            date = result.get(date_field)
            if isinstance(date, str) and date.startswith(prefix):
                return result
        return None

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
        """Fetch one locale's translated movie fields, or ``None`` on failure."""
        resp = await self._client.get(
            f"{self._base_url}/movie/{tmdb_id}",
            params=self._params(
                language=locale,
                append_to_response="images",
                include_image_language=f"{locale},en,null",
            ),
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        return LocalizedFields(
            title=data.get("title"),
            synopsis=data.get("overview"),
            tagline=data.get("tagline") or None,
            genres=[g["name"] for g in data.get("genres", [])],
            logo_url=self._pick_best_logo_url(data.get("images", {}).get("logos"), locale),
            poster_url=self._image_url(data.get("poster_path")),
            backdrop_url=self._image_url(data.get("backdrop_path")),
        )

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
        ``parts`` array — one entry per member title with
        ``id`` / ``title`` / ``release_date`` / ``overview`` /
        ``poster_path`` / ``backdrop_path`` / ``vote_average``. Each
        part is mapped onto :class:`CollectionPartMetadata`; missing
        fields are tolerated.

        404 / network errors / non-dict payloads degrade to ``None``
        so the use case can render an "unavailable" state rather
        than 500.
        """
        try:
            resp = await self._client.get(
                f"{self._base_url}/collection/{tmdb_id}",
                params=self._params(language=language),
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, dict):
            return None

        raw_id = data.get("id")
        name = data.get("name")
        if not isinstance(raw_id, int) or not isinstance(name, str):
            return None

        parts_raw = data.get("parts") or []
        parts: list[CollectionPartMetadata] = []
        if isinstance(parts_raw, list):
            for part in parts_raw:
                shaped = self._shape_collection_part(part)
                if shaped is not None:
                    parts.append(shaped)

        return CollectionDetailMetadata(
            tmdb_id=raw_id,
            name=name,
            overview=str(data.get("overview")) if data.get("overview") else None,
            poster_url=self._image_url(
                str(data.get("poster_path")) if data.get("poster_path") else None,
            ),
            backdrop_url=self._image_url(
                str(data.get("backdrop_path")) if data.get("backdrop_path") else None,
            ),
            parts=parts,
        )

    def _shape_collection_part(
        self,
        part: object,
    ) -> CollectionPartMetadata | None:
        """Convert a ``/collection/{id}`` ``parts`` entry to a part DTO.

        Drops any entry without a usable ``id`` + ``title`` since the
        UI cannot render those rows. Year is parsed from
        ``release_date`` when present; ``vote_average`` is forwarded
        as-is so 0.0 (TMDB's "no rating yet" signal) reaches the use
        case which can decide to hide the star.
        """
        if not isinstance(part, dict):
            return None
        raw_id = part.get("id")
        title = part.get("title") or part.get("original_title")
        if not isinstance(raw_id, int) or not isinstance(title, str) or not title:
            return None

        year: int | None = None
        release_date = part.get("release_date")
        if isinstance(release_date, str) and len(release_date) >= 4:
            try:
                year = int(release_date[:4])
            except ValueError:
                year = None

        rating: float | None = None
        vote = part.get("vote_average")
        if isinstance(vote, int | float) and vote > 0:
            rating = float(vote)

        return CollectionPartMetadata(
            tmdb_id=raw_id,
            title=title,
            year=year,
            synopsis=str(part.get("overview")) if part.get("overview") else None,
            poster_url=self._image_url(
                str(part.get("poster_path")) if part.get("poster_path") else None,
            ),
            backdrop_url=self._image_url(
                str(part.get("backdrop_path")) if part.get("backdrop_path") else None,
            ),
            rating=rating,
        )

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
            resp = await self._client.get(
                f"{self._base_url}/movie/{tmdb_id}",
                params=self._params(),
            )
        except httpx.HTTPError:
            return []
        if resp.status_code != 200:
            return []

        coll = resp.json().get("belongs_to_collection")
        if not isinstance(coll, dict):
            return []
        coll_id = coll.get("id")
        if not isinstance(coll_id, int):
            return []

        try:
            resp = await self._client.get(
                f"{self._base_url}/collection/{coll_id}",
                params=self._params(),
            )
        except httpx.HTTPError:
            return []
        if resp.status_code != 200:
            return []

        parts = resp.json().get("parts") or []
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
            resp = await self._client.get(
                f"{self._base_url}/{media_type}/{tmdb_id}/{endpoint}",
                params=self._params(),
            )
        except httpx.HTTPError:
            return []
        if resp.status_code != 200:
            return []
        results = resp.json().get("results") or []
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
        from dataclasses import replace

        return replace(meta, biography=en_meta.biography)

    async def _fetch_person(self, tmdb_id: int, language: str) -> PersonMetadata | None:
        """Single ``/person/{id}`` round-trip in ``language``."""
        try:
            resp = await self._client.get(
                f"{self._base_url}/person/{tmdb_id}",
                params=self._params(language=language),
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, dict):
            return None
        # ``id`` and ``name`` are required for the UI to render
        # anything useful; everything else is optional polish.
        raw_id = data.get("id")
        if not isinstance(raw_id, int):
            return None
        name = str(data.get("name", "")).strip()
        if not name:
            return None
        return PersonMetadata(
            tmdb_id=raw_id,
            name=name,
            biography=str(data.get("biography") or ""),
            birthday=str(data.get("birthday")) if data.get("birthday") else None,
            deathday=str(data.get("deathday")) if data.get("deathday") else None,
            place_of_birth=(
                str(data.get("place_of_birth")) if data.get("place_of_birth") else None
            ),
            known_for_department=(
                str(data.get("known_for_department")) if data.get("known_for_department") else None
            ),
            profile_path=self._image_url(
                str(data.get("profile_path")) if data.get("profile_path") else None
            ),
        )

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
            resp = await self._client.get(
                f"{self._base_url}/{path}/{tmdb_id}/translations",
                params=self._params(),
            )
        except httpx.HTTPError:
            return {}
        if resp.status_code != 200:
            return {}

        translations = resp.json().get("translations", [])
        titles: dict[str, str] = {}
        for locale in self._supported_locales:
            title = _pick_translation_title(translations, locale, title_key)
            if title:
                titles[locale] = title
        return titles

    async def _fetch_series_localized_fields(
        self, tmdb_id: int, locale: str
    ) -> LocalizedFields | None:
        """Fetch one locale's translated series fields, or ``None`` on failure."""
        resp = await self._client.get(
            f"{self._base_url}/tv/{tmdb_id}",
            params=self._params(
                language=locale,
                append_to_response="images",
                include_image_language=f"{locale},en,null",
            ),
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        return LocalizedFields(
            title=data.get("name"),
            synopsis=data.get("overview"),
            genres=[g["name"] for g in data.get("genres", [])],
            logo_url=self._pick_best_logo_url(data.get("images", {}).get("logos"), locale),
            poster_url=self._image_url(data.get("poster_path")),
            backdrop_url=self._image_url(data.get("backdrop_path")),
        )

    async def _fetch_movie_details(
        self, tmdb_id: int, language: str = "en-US"
    ) -> MediaMetadata | None:
        """Fetch full movie details from TMDB.

        ``images`` is appended to the response (with
        ``include_image_language`` filtered to the requested language,
        English, and language-neutral) so the title logo comes back
        in the same round-trip — saves a separate HTTP call per
        details fetch.
        """
        resp = await self._client.get(
            f"{self._base_url}/movie/{tmdb_id}",
            params=self._params(
                append_to_response="credits,release_dates,videos,images",
                language=language,
                include_image_language=f"{language},en,null",
            ),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

        year = None
        if data.get("release_date"):
            year = int(data["release_date"][:4])

        credits = data.get("credits", {})
        cast = self._parse_cast(credits.get("cast", []))
        directors, writers = self._parse_crew(credits.get("crew", []))
        content_rating = self._parse_content_rating(data.get("release_dates", {}))
        trailer_url = self._parse_trailer(data.get("videos", {}))

        logo_url = self._pick_best_logo_url(data.get("images", {}).get("logos"), language)
        collection = await self._fetch_collection_metadata(data.get("belongs_to_collection"))
        return MediaMetadata(
            title=data.get("title", ""),
            original_title=data.get("original_title"),
            year=year,
            duration_seconds=(data.get("runtime") or 0) * 60,
            synopsis=data.get("overview"),
            tagline=data.get("tagline") or None,
            poster_url=self._image_url(data.get("poster_path")),
            backdrop_url=self._image_url(data.get("backdrop_path")),
            logo_url=logo_url,
            genres=[g["name"] for g in data.get("genres", [])],
            tmdb_id=data["id"],
            imdb_id=data.get("imdb_id"),
            cast=cast,
            directors=directors,
            writers=writers,
            content_rating=content_rating.value if content_rating else None,
            trailer_url=trailer_url,
            collection=collection,
        )

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
            resp = await self._client.get(
                f"{self._base_url}/collection/{coll_id}",
                params=self._params(),
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        parts = resp.json().get("parts") or []
        return CollectionMetadata(tmdb_id=coll_id, name=name, parts_count=len(parts))

    async def _fetch_series_details(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch full series details including seasons and episodes.

        Same trick as ``_fetch_movie_details``: ``images`` is appended
        so the title logo comes back in this round-trip; default
        language is English since the bulk of the series-details flow
        is English-first (the localized variant overrides on top).
        """
        resp = await self._client.get(
            f"{self._base_url}/tv/{tmdb_id}",
            params=self._params(
                append_to_response="external_ids,content_ratings,videos,images,credits",
                include_image_language="en,null",
            ),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

        # Top-billed cast comes back nested under ``credits.cast`` thanks
        # to the ``credits`` append above. Reuse the same parser the
        # movie path uses so series and movies share the cap/order rules.
        credits = data.get("credits", {})
        cast = self._parse_cast(credits.get("cast", []))

        start_year = None
        if data.get("first_air_date"):
            start_year = int(data["first_air_date"][:4])

        end_year = None
        if data.get("last_air_date") and data.get("status") == "Ended":
            end_year = int(data["last_air_date"][:4])

        # Fetch season details with episodes
        seasons: list[SeasonMetadata] = []
        for s in data.get("seasons", []):
            season_num = s.get("season_number", 0)
            season_meta = await self._fetch_season(tmdb_id, season_num)
            if season_meta:
                seasons.append(season_meta)

        content_rating = self._parse_series_content_rating(
            data.get("content_ratings", {}),
        )

        logo_url = self._pick_best_logo_url(data.get("images", {}).get("logos"), "en")
        return MediaMetadata(
            title=data.get("name", ""),
            original_title=data.get("original_name"),
            year=start_year,
            end_year=end_year,
            synopsis=data.get("overview"),
            poster_url=self._image_url(data.get("poster_path")),
            backdrop_url=self._image_url(data.get("backdrop_path")),
            logo_url=logo_url,
            genres=[g["name"] for g in data.get("genres", [])],
            cast=cast,
            tmdb_id=data["id"],
            imdb_id=data.get("external_ids", {}).get("imdb_id"),
            content_rating=content_rating.value if content_rating else None,
            trailer_url=self._parse_trailer(data.get("videos", {})),
            seasons=seasons,
        )

    async def _fetch_season(self, series_id: int, season_number: int) -> SeasonMetadata | None:
        """Fetch season details + episodes with per-locale title/synopsis overlays.

        The English payload is the base; each configured non-English
        locale is fetched **concurrently** (one ``/season/{n}?language=``
        round-trip per locale) and folded into per-season and
        per-episode ``localized`` overrides keyed by BCP-47 tag. A
        locale fetch that fails is skipped — the English base still
        returns. Seasons themselves are fetched sequentially by the
        caller; only this locale fan-out is concurrent.
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

        episodes = [
            EpisodeMetadata(
                season_number=season_number,
                episode_number=ep.get("episode_number", 0),
                title=ep.get("name"),
                synopsis=ep.get("overview"),
                air_date=ep.get("air_date"),
                duration_seconds=(ep.get("runtime") or 0) * 60,
                still_url=self._image_url(ep.get("still_path")),
                localized=self._episode_localized(ep.get("episode_number", 0), loc_payloads),
            )
            for ep in base.get("episodes", [])
        ]

        return SeasonMetadata(
            season_number=season_number,
            title=base.get("name"),
            synopsis=base.get("overview"),
            poster_url=self._image_url(base.get("poster_path")),
            air_date=base.get("air_date"),
            episodes=episodes,
            localized=self._text_localized(loc_payloads),
        )

    async def _fetch_season_payload(
        self, series_id: int, season_number: int, language: str | None
    ) -> dict[str, Any] | None:
        """One ``/season/{n}`` round-trip; ``None`` on 404 or locale-overlay failure.

        ``language=None`` is the English base — a non-404 error there
        is fatal (raised). For a localized overlay any non-200 simply
        drops that locale.
        """
        resp = await self._client.get(
            f"{self._base_url}/tv/{series_id}/season/{season_number}",
            params=self._params(language=language),
        )
        if resp.status_code == 404:
            return None
        if language is not None and resp.status_code != 200:
            return None
        if language is None:
            resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    @staticmethod
    def _episode_localized(
        episode_number: int, loc_payloads: dict[str, dict[str, Any]]
    ) -> dict[str, LocalizedTextFields]:
        """Build per-locale title/synopsis overrides for one episode."""
        localized: dict[str, LocalizedTextFields] = {}
        for locale, payload in loc_payloads.items():
            loc_ep = _episode_payload_by_number(payload, episode_number)
            if loc_ep is None:
                continue
            fields = LocalizedTextFields(title=loc_ep.get("name"), synopsis=loc_ep.get("overview"))
            if fields.title or fields.synopsis:
                localized[locale] = fields
        return localized

    @staticmethod
    def _text_localized(
        loc_payloads: dict[str, dict[str, Any]],
    ) -> dict[str, LocalizedTextFields]:
        """Build per-locale title/synopsis overrides for the season itself."""
        localized: dict[str, LocalizedTextFields] = {}
        for locale, payload in loc_payloads.items():
            fields = LocalizedTextFields(
                title=payload.get("name"), synopsis=payload.get("overview")
            )
            if fields.title or fields.synopsis:
                localized[locale] = fields
        return localized

    def _parse_cast(self, cast_data: list[dict[str, object]]) -> list[CreditPerson]:
        """Parse TMDB cast data into CreditPerson list (top billed)."""
        sorted_cast = sorted(cast_data, key=lambda c: _safe_int(c.get("order"), 999))
        return [
            self._to_credit_person(c, role_key="character")
            for c in sorted_cast[:_MAX_CAST]
            if c.get("name")
        ]

    def _parse_crew(
        self, crew_data: list[dict[str, object]]
    ) -> tuple[list[CreditPerson], list[CreditPerson]]:
        """Parse TMDB crew data into directors and writers lists."""
        directors: list[CreditPerson] = []
        writers: list[CreditPerson] = []
        seen_directors: set[str] = set()
        seen_writers: set[str] = set()

        for c in crew_data:
            name = str(c.get("name", ""))
            if not name:
                continue
            job = str(c.get("job", "")).lower()
            dept = str(c.get("department", "")).lower()
            if job == "director" and name not in seen_directors:
                directors.append(self._to_credit_person(c, role_key="job"))
                seen_directors.add(name)
            elif dept == "writing" and name not in seen_writers:
                writers.append(self._to_credit_person(c, role_key="job"))
                seen_writers.add(name)

        return directors, writers

    @staticmethod
    def _parse_content_rating(release_dates: dict[str, object]) -> ContentRating | None:
        """Extract content rating from TMDB release_dates, preferring BR then US."""
        results = release_dates.get("results", [])
        if not isinstance(results, list):
            return None

        ratings_by_country: dict[str, str] = {}
        for entry in results:
            iso = str(entry.get("iso_3166_1", "")) if isinstance(entry, dict) else ""
            release_list = entry.get("release_dates", []) if isinstance(entry, dict) else []
            if not isinstance(release_list, list):
                continue
            for rel in release_list:
                cert = str(rel.get("certification", "")).strip() if isinstance(rel, dict) else ""
                if cert and iso not in ratings_by_country:
                    ratings_by_country[iso] = cert

        selected = ratings_by_country.get("BR") or ratings_by_country.get("US")
        return ContentRating(selected) if selected else None

    @staticmethod
    def _parse_trailer(videos: dict[str, object]) -> str | None:
        """Extract the best YouTube trailer URL from TMDB videos.

        Ranking: official Trailer > any Trailer > official Teaser > any Teaser.
        """
        results = videos.get("results", [])
        if not isinstance(results, list):
            return None

        candidates: list[dict[str, object]] = [
            v
            for v in results
            if isinstance(v, dict)
            and v.get("site") == "YouTube"
            and v.get("type") in ("Trailer", "Teaser")
            and v.get("key")
        ]

        if not candidates:
            return None

        def _rank(video: dict[str, object]) -> int:
            is_trailer = video.get("type") == "Trailer"
            is_official = bool(video.get("official"))
            if is_trailer and is_official:
                return 0
            if is_trailer:
                return 1
            if is_official:
                return 2
            return 3

        ranked = sorted(enumerate(candidates), key=lambda item: (_rank(item[1]), item[0]))
        best = ranked[0][1]

        return f"https://www.youtube.com/watch?v={best['key']}"

    @staticmethod
    def _parse_series_content_rating(content_ratings: dict[str, object]) -> ContentRating | None:
        """Extract content rating from TMDB series content_ratings, preferring BR then US."""
        results = content_ratings.get("results", [])
        if not isinstance(results, list):
            return None

        ratings_by_country: dict[str, str] = {}
        for entry in results:
            if not isinstance(entry, dict):
                continue
            iso = str(entry.get("iso_3166_1", ""))
            rating = str(entry.get("rating", "")).strip()
            if rating and iso not in ratings_by_country:
                ratings_by_country[iso] = rating

        selected = ratings_by_country.get("BR") or ratings_by_country.get("US")
        return ContentRating(selected) if selected else None

    def _to_credit_person(self, data: dict[str, object], role_key: str) -> CreditPerson:
        """Convert a TMDB cast/crew dict to a CreditPerson."""
        profile_path = str(data.get("profile_path", "")) or None
        return CreditPerson(
            name=str(data.get("name", "")),
            role=str(data.get(role_key, "")) or None,
            profile_url=self._image_url(profile_path),
            tmdb_id=int(str(data["id"])) if data.get("id") else None,
        )


def _extract_year_prefix(value: object) -> int | None:
    """Return the 4-digit year prefix of an ISO date string, or ``None``.

    Both ``release_date`` (movies) and ``first_air_date`` (TV) come
    in as ``"YYYY-MM-DD"`` — or empty/missing for poorly catalogued
    entries. Defensive parsing here avoids ``ValueError`` polluting
    the picker payload when TMDB returns ``""`` or no field at all.
    """
    if not isinstance(value, str) or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def _to_movie_candidate(
    raw: dict[str, object],
    image_url: Callable[[str | None], str | None],
) -> SearchCandidate:
    title = str(raw.get("title") or raw.get("original_title") or "")
    overview_raw = raw.get("overview")
    overview = str(overview_raw) if overview_raw else None
    poster = raw.get("poster_path")
    return SearchCandidate(
        tmdb_id=int(str(raw["id"])),
        media_type="movie",
        title=title,
        year=_extract_year_prefix(raw.get("release_date")),
        overview=overview,
        poster_url=image_url(str(poster)) if isinstance(poster, str) else None,
    )


def _to_series_candidate(
    raw: dict[str, object],
    image_url: Callable[[str | None], str | None],
) -> SearchCandidate:
    title = str(raw.get("name") or raw.get("original_name") or "")
    overview_raw = raw.get("overview")
    overview = str(overview_raw) if overview_raw else None
    poster = raw.get("poster_path")
    return SearchCandidate(
        tmdb_id=int(str(raw["id"])),
        media_type="tv",
        title=title,
        year=_extract_year_prefix(raw.get("first_air_date")),
        overview=overview,
        poster_url=image_url(str(poster)) if isinstance(poster, str) else None,
    )


__all__ = ["TmdbClient"]
