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
        """Fetch movie details in English with pt-BR localization."""
        en_meta = await self._fetch_movie_details(tmdb_id, language="en-US")
        if not en_meta:
            return None

        pt_resp = await self._client.get(
            f"{self._base_url}/movie/{tmdb_id}",
            params=self._params(language="pt-BR"),
        )
        if pt_resp.status_code != 200:
            return en_meta

        pt_data = pt_resp.json()
        pt_fields = LocalizedFields(
            title=pt_data.get("title"),
            synopsis=pt_data.get("overview"),
            genres=[g["name"] for g in pt_data.get("genres", [])],
        )

        from dataclasses import replace

        return replace(en_meta, localized={"pt-BR": pt_fields})

    async def get_series_by_id(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch series details by TMDB ID."""
        return await self._fetch_series_details(tmdb_id)

    async def get_series_localized(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch series details in English with pt-BR localization."""
        en_meta = await self._fetch_series_details(tmdb_id)
        if not en_meta:
            return None

        pt_resp = await self._client.get(
            f"{self._base_url}/tv/{tmdb_id}",
            params=self._params(language="pt-BR"),
        )
        if pt_resp.status_code != 200:
            return en_meta

        pt_data = pt_resp.json()
        pt_fields = LocalizedFields(
            title=pt_data.get("name"),
            synopsis=pt_data.get("overview"),
            genres=[g["name"] for g in pt_data.get("genres", [])],
        )

        from dataclasses import replace

        return replace(en_meta, localized={"pt-BR": pt_fields})

    async def _fetch_movie_details(
        self, tmdb_id: int, language: str = "en-US"
    ) -> MediaMetadata | None:
        """Fetch full movie details from TMDB."""
        resp = await self._client.get(
            f"{self._base_url}/movie/{tmdb_id}",
            params=self._params(append_to_response="credits,release_dates", language=language),
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

        return MediaMetadata(
            title=data.get("title", ""),
            original_title=data.get("original_title"),
            year=year,
            duration_seconds=(data.get("runtime") or 0) * 60,
            synopsis=data.get("overview"),
            poster_url=self._image_url(data.get("poster_path")),
            backdrop_url=self._image_url(data.get("backdrop_path")),
            genres=[g["name"] for g in data.get("genres", [])],
            tmdb_id=data["id"],
            imdb_id=data.get("imdb_id"),
            cast=cast,
            directors=directors,
            writers=writers,
            content_rating=content_rating,
        )

    async def _fetch_series_details(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch full series details including seasons and episodes."""
        resp = await self._client.get(
            f"{self._base_url}/tv/{tmdb_id}",
            params=self._params(append_to_response="external_ids"),
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

        return MediaMetadata(
            title=data.get("name", ""),
            original_title=data.get("original_name"),
            year=start_year,
            end_year=end_year,
            synopsis=data.get("overview"),
            poster_url=self._image_url(data.get("poster_path")),
            backdrop_url=self._image_url(data.get("backdrop_path")),
            genres=[g["name"] for g in data.get("genres", [])],
            tmdb_id=data["id"],
            imdb_id=data.get("external_ids", {}).get("imdb_id"),
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
    def _parse_content_rating(release_dates: dict[str, object]) -> str | None:
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

        return ratings_by_country.get("BR") or ratings_by_country.get("US") or None

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
