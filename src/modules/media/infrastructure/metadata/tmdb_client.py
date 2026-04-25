"""TMDB API client implementing MetadataProvider port."""

import httpx

from src.modules.media.application.ports import (
    CreditPerson,
    EpisodeMetadata,
    LocalizedFields,
    MediaMetadata,
    MetadataProvider,
    SeasonMetadata,
)
from src.modules.media.domain.value_objects import ContentRating

_MAX_CAST = 15


def _safe_int(value: object, default: int) -> int:
    """Safely convert a value to int, returning default on failure."""
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return default


_TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"


class TmdbClient(MetadataProvider):
    """The Movie Database (TMDB) API client.

    Args:
        api_key: TMDB API key (v3 auth).
        base_url: TMDB API base URL.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.themoviedb.org/3") -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

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
        """Search TMDB for a movie and return metadata for the best match."""
        resp = await self._client.get(
            f"{self._base_url}/search/movie",
            params=self._params(query=title, year=year),
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        if not results:
            return None

        tmdb_id = results[0]["id"]
        return await self._fetch_movie_details(tmdb_id)

    async def search_series(self, title: str, year: int | None = None) -> MediaMetadata | None:
        """Search TMDB for a TV series and return metadata for the best match."""
        resp = await self._client.get(
            f"{self._base_url}/search/tv",
            params=self._params(query=title, first_air_date_year=year),
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        if not results:
            return None

        tmdb_id = results[0]["id"]
        return await self._fetch_series_details(tmdb_id)

    async def get_movie_by_id(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch movie details by TMDB ID."""
        return await self._fetch_movie_details(tmdb_id)

    async def get_movie_localized(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch movie details in English with pt-BR localization.

        The pt-BR details call also appends ``images`` filtered to
        pt-BR / en / language-neutral, so the localized logo comes
        back in the same round-trip. ``Movie.get_logo_path(lang)``
        picks the localized one when present and falls back to the
        global (en) otherwise — same shape as title/synopsis.
        """
        en_meta = await self._fetch_movie_details(tmdb_id, language="en-US")
        if not en_meta:
            return None

        pt_resp = await self._client.get(
            f"{self._base_url}/movie/{tmdb_id}",
            params=self._params(
                language="pt-BR",
                append_to_response="images",
                include_image_language="pt-BR,en,null",
            ),
        )
        if pt_resp.status_code != 200:
            return en_meta

        pt_data = pt_resp.json()
        pt_fields = LocalizedFields(
            title=pt_data.get("title"),
            synopsis=pt_data.get("overview"),
            genres=[g["name"] for g in pt_data.get("genres", [])],
            logo_url=self._pick_best_logo_url(pt_data.get("images", {}).get("logos"), "pt-BR"),
        )

        from dataclasses import replace

        return replace(en_meta, localized={"pt-BR": pt_fields})

    async def get_series_by_id(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch series details by TMDB ID."""
        return await self._fetch_series_details(tmdb_id)

    async def get_movie_recommendations(self, tmdb_id: int) -> list[int]:
        """Return TMDB ids of movies recommended for ``tmdb_id``.

        TMDB exposes two related-content endpoints for movies:

        - ``/movie/{id}/recommendations`` — ML-based, often empty for
          obscure titles.
        - ``/movie/{id}/similar`` — heuristic (genre / keyword
          overlap), almost always populated.

        We try ``recommendations`` first; if it returns nothing
        useful, fall back to ``similar`` so the "you might also like"
        section never goes blank just because TMDB hasn't built up
        signal for that title yet.

        Network failures and unexpected payload shapes degrade to an
        empty list — recommendation rendering is best-effort polish,
        never load-bearing.
        """
        ids = await self._fetch_related_movie_ids(tmdb_id, "recommendations")
        if not ids:
            ids = await self._fetch_related_movie_ids(tmdb_id, "similar")
        return ids

    async def _fetch_related_movie_ids(self, tmdb_id: int, endpoint: str) -> list[int]:
        """Hit a single ``/movie/{id}/<endpoint>`` and extract numeric ids.

        ``endpoint`` is ``"recommendations"`` or ``"similar"``; both
        paginate but page 1 already carries enough candidates for the
        UI's ~10-item carousel and a second request would just burn
        latency on results we'd discard.
        """
        try:
            resp = await self._client.get(
                f"{self._base_url}/movie/{tmdb_id}/{endpoint}",
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

    async def get_series_localized(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch series details in English with pt-BR localization.

        Same one-round-trip-per-language pattern as
        ``get_movie_localized`` — the pt-BR details call appends
        ``images`` so the localized logo comes back without an extra
        HTTP fetch.
        """
        en_meta = await self._fetch_series_details(tmdb_id)
        if not en_meta:
            return None

        pt_resp = await self._client.get(
            f"{self._base_url}/tv/{tmdb_id}",
            params=self._params(
                language="pt-BR",
                append_to_response="images",
                include_image_language="pt-BR,en,null",
            ),
        )
        if pt_resp.status_code != 200:
            return en_meta

        pt_data = pt_resp.json()
        pt_fields = LocalizedFields(
            title=pt_data.get("name"),
            synopsis=pt_data.get("overview"),
            genres=[g["name"] for g in pt_data.get("genres", [])],
            logo_url=self._pick_best_logo_url(pt_data.get("images", {}).get("logos"), "pt-BR"),
        )

        from dataclasses import replace

        return replace(en_meta, localized={"pt-BR": pt_fields})

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
        return MediaMetadata(
            title=data.get("title", ""),
            original_title=data.get("original_title"),
            year=year,
            duration_seconds=(data.get("runtime") or 0) * 60,
            synopsis=data.get("overview"),
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
        )

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
                append_to_response="external_ids,content_ratings,videos,images",
                include_image_language="en,null",
            ),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

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
            tmdb_id=data["id"],
            imdb_id=data.get("external_ids", {}).get("imdb_id"),
            content_rating=content_rating.value if content_rating else None,
            trailer_url=self._parse_trailer(data.get("videos", {})),
            seasons=seasons,
        )

    async def _fetch_season(self, series_id: int, season_number: int) -> SeasonMetadata | None:
        """Fetch season details with episode list."""
        resp = await self._client.get(
            f"{self._base_url}/tv/{series_id}/season/{season_number}",
            params=self._params(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

        episodes = [
            EpisodeMetadata(
                season_number=season_number,
                episode_number=ep.get("episode_number", 0),
                title=ep.get("name"),
                synopsis=ep.get("overview"),
                air_date=ep.get("air_date"),
                duration_seconds=(ep.get("runtime") or 0) * 60,
                still_url=self._image_url(ep.get("still_path")),
            )
            for ep in data.get("episodes", [])
        ]

        return SeasonMetadata(
            season_number=season_number,
            title=data.get("name"),
            synopsis=data.get("overview"),
            poster_url=self._image_url(data.get("poster_path")),
            air_date=data.get("air_date"),
            episodes=episodes,
        )

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


__all__ = ["TmdbClient"]
