"""TMDB API client implementing MetadataProvider port."""

import httpx

from src.modules.media.application.ports import (
    EpisodeMetadata,
    MediaMetadata,
    MetadataProvider,
    SeasonMetadata,
)

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
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/search/movie",
                params=self._params(query=title, year=year),
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

            if not results:
                return None

            tmdb_id = results[0]["id"]
            return await self._fetch_movie_details(client, tmdb_id)

    async def search_series(self, title: str, year: int | None = None) -> MediaMetadata | None:
        """Search TMDB for a TV series and return metadata for the best match."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/search/tv",
                params=self._params(query=title, first_air_date_year=year),
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

            if not results:
                return None

            tmdb_id = results[0]["id"]
            return await self._fetch_series_details(client, tmdb_id)

    async def get_movie_by_id(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch movie details by TMDB ID."""
        async with httpx.AsyncClient() as client:
            return await self._fetch_movie_details(client, tmdb_id)

    async def get_series_by_id(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch series details by TMDB ID."""
        async with httpx.AsyncClient() as client:
            return await self._fetch_series_details(client, tmdb_id)

    async def _fetch_movie_details(
        self, client: httpx.AsyncClient, tmdb_id: int
    ) -> MediaMetadata | None:
        """Fetch full movie details from TMDB."""
        resp = await client.get(
            f"{self._base_url}/movie/{tmdb_id}",
            params=self._params(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

        year = None
        if data.get("release_date"):
            year = int(data["release_date"][:4])

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
        )

    async def _fetch_series_details(
        self, client: httpx.AsyncClient, tmdb_id: int
    ) -> MediaMetadata | None:
        """Fetch full series details including seasons and episodes."""
        resp = await client.get(
            f"{self._base_url}/tv/{tmdb_id}",
            params=self._params(),
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
            season_meta = await self._fetch_season(client, tmdb_id, season_num)
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

    async def _fetch_season(
        self, client: httpx.AsyncClient, series_id: int, season_number: int
    ) -> SeasonMetadata | None:
        """Fetch season details with episode list."""
        resp = await client.get(
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


__all__ = ["TmdbClient"]
