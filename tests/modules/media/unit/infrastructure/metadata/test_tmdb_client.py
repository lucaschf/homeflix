"""Tests for TmdbClient."""

import itertools
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.modules.media.domain.value_objects import ContentRating
from src.modules.media.infrastructure.metadata.tmdb_client import (
    TmdbClient,
    _safe_int,
)


def _build_response(status_code: int = 200, json_data: dict[str, Any] | None = None) -> MagicMock:
    """Build a mocked httpx Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=response
        )
    return response


def _make_client(get_responses: list[MagicMock] | MagicMock | None = None) -> TmdbClient:
    """Build a TmdbClient with a mocked HTTP client.

    For list-mode fixtures, the helper appends an infinite tail of
    ``{"logos": []}`` responses so newly-added side calls — e.g. the
    ``/images`` fetch the production code does to populate
    ``logo_url`` — never exhaust the queue. Tests that need to assert
    on the logo fetch can still inject a specific response inside the
    list before the queue runs out.
    """
    client = TmdbClient(api_key="test-key")
    mock_http = MagicMock()
    if isinstance(get_responses, list):
        empty_logos_tail = itertools.repeat(_build_response(json_data={"logos": []}))
        mock_http.get = AsyncMock(
            side_effect=itertools.chain(get_responses, empty_logos_tail),
        )
    elif get_responses is not None:
        mock_http.get = AsyncMock(return_value=get_responses)
    else:
        mock_http.get = AsyncMock()
    client._client = mock_http
    return client


def _movie_details(tmdb_id: int = 27205, title: str = "Inception") -> dict[str, Any]:
    return {
        "id": tmdb_id,
        "title": title,
        "original_title": title,
        "overview": "A thief who steals corporate secrets through dreams.",
        "release_date": "2010-07-16",
        "runtime": 148,
        "poster_path": "/poster.jpg",
        "backdrop_path": "/backdrop.jpg",
        "genres": [{"name": "Sci-Fi"}, {"name": "Action"}],
        "imdb_id": "tt1375666",
        "credits": {
            "cast": [
                {"name": "Leonardo DiCaprio", "character": "Cobb", "order": 0, "id": 6193},
            ],
            "crew": [
                {
                    "name": "Christopher Nolan",
                    "job": "Director",
                    "department": "Directing",
                    "id": 525,
                },
                {
                    "name": "Christopher Nolan",
                    "job": "Writer",
                    "department": "Writing",
                    "id": 525,
                },
            ],
        },
        "release_dates": {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [{"certification": "PG-13"}],
                },
            ],
        },
        "videos": {
            "results": [
                {"site": "YouTube", "type": "Trailer", "key": "abc123", "official": True},
            ],
        },
    }


def _series_details(tmdb_id: int = 1396) -> dict[str, Any]:
    return {
        "id": tmdb_id,
        "name": "Breaking Bad",
        "original_name": "Breaking Bad",
        "overview": "A chemistry teacher turns to crime.",
        "first_air_date": "2008-01-20",
        "last_air_date": "2013-09-29",
        "status": "Ended",
        "poster_path": "/poster.jpg",
        "backdrop_path": "/backdrop.jpg",
        "genres": [{"name": "Drama"}],
        "external_ids": {"imdb_id": "tt0903747"},
        "seasons": [{"season_number": 1}],
        "content_ratings": {
            "results": [{"iso_3166_1": "US", "rating": "TV-MA"}],
        },
        "videos": {"results": []},
    }


def _season_details(season_number: int = 1) -> dict[str, Any]:
    return {
        "name": f"Season {season_number}",
        "overview": "Season overview.",
        "poster_path": "/season_poster.jpg",
        "air_date": "2008-01-20",
        "episodes": [
            {
                "episode_number": 1,
                "name": "Pilot",
                "overview": "Walter White begins.",
                "air_date": "2008-01-20",
                "runtime": 58,
                "still_path": "/still.jpg",
            },
        ],
    }


@pytest.mark.unit
class TestSafeInt:
    """Tests for _safe_int helper."""

    def test_should_convert_int(self) -> None:
        assert _safe_int(42, default=0) == 42

    def test_should_convert_string_int(self) -> None:
        assert _safe_int("42", default=0) == 42

    def test_should_return_default_for_invalid(self) -> None:
        assert _safe_int("abc", default=99) == 99

    def test_should_return_default_for_none(self) -> None:
        assert _safe_int(None, default=5) == 5


@pytest.mark.unit
class TestTmdbClientParams:
    """Tests for _params and _image_url helpers."""

    def test_params_should_include_api_key(self) -> None:
        client = _make_client()
        params = client._params()
        assert params == {"api_key": "test-key"}

    def test_params_should_include_extra(self) -> None:
        client = _make_client()
        params = client._params(query="Inception", year=2010)
        assert params == {"api_key": "test-key", "query": "Inception", "year": 2010}

    def test_params_should_skip_none_values(self) -> None:
        client = _make_client()
        params = client._params(query="Inception", year=None)
        assert "year" not in params
        assert params["query"] == "Inception"

    def test_image_url_should_prefix_cdn(self) -> None:
        client = _make_client()
        assert client._image_url("/poster.jpg") == "https://image.tmdb.org/t/p/original/poster.jpg"

    def test_image_url_should_return_none_for_none(self) -> None:
        client = _make_client()
        assert client._image_url(None) is None

    def test_image_url_should_return_none_for_empty(self) -> None:
        client = _make_client()
        assert client._image_url("") is None


@pytest.mark.unit
class TestParseContentRating:
    """Tests for _parse_content_rating static method."""

    def test_should_prefer_br_over_us(self) -> None:
        data: dict[str, Any] = {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [{"certification": "PG-13"}],
                },
                {
                    "iso_3166_1": "BR",
                    "release_dates": [{"certification": "14"}],
                },
            ],
        }
        assert TmdbClient._parse_content_rating(data) == ContentRating("14")

    def test_should_fallback_to_us(self) -> None:
        data: dict[str, Any] = {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [{"certification": "PG-13"}],
                },
            ],
        }
        assert TmdbClient._parse_content_rating(data) == ContentRating("PG-13")

    def test_should_return_none_when_empty(self) -> None:
        assert TmdbClient._parse_content_rating({"results": []}) is None

    def test_should_return_none_when_missing_key(self) -> None:
        assert TmdbClient._parse_content_rating({}) is None

    def test_should_handle_invalid_results_type(self) -> None:
        assert TmdbClient._parse_content_rating({"results": "bad"}) is None

    def test_should_skip_empty_certifications(self) -> None:
        data: dict[str, Any] = {
            "results": [
                {
                    "iso_3166_1": "BR",
                    "release_dates": [{"certification": ""}],
                },
                {
                    "iso_3166_1": "US",
                    "release_dates": [{"certification": "R"}],
                },
            ],
        }
        assert TmdbClient._parse_content_rating(data) == ContentRating("R")


@pytest.mark.unit
class TestParseSeriesContentRating:
    """Tests for _parse_series_content_rating."""

    def test_should_prefer_br(self) -> None:
        data: dict[str, Any] = {
            "results": [
                {"iso_3166_1": "US", "rating": "TV-MA"},
                {"iso_3166_1": "BR", "rating": "18"},
            ],
        }
        assert TmdbClient._parse_series_content_rating(data) == ContentRating("18")

    def test_should_fallback_to_us(self) -> None:
        data: dict[str, Any] = {"results": [{"iso_3166_1": "US", "rating": "TV-14"}]}
        assert TmdbClient._parse_series_content_rating(data) == ContentRating("TV-14")

    def test_should_return_none_when_empty(self) -> None:
        assert TmdbClient._parse_series_content_rating({}) is None

    def test_should_handle_invalid_results_type(self) -> None:
        assert TmdbClient._parse_series_content_rating({"results": "bad"}) is None


@pytest.mark.unit
class TestParseTrailer:
    """Tests for _parse_trailer static method."""

    def test_should_pick_official_youtube_trailer(self) -> None:
        videos: dict[str, Any] = {
            "results": [
                {"site": "YouTube", "type": "Trailer", "key": "abc", "official": True},
            ],
        }
        assert TmdbClient._parse_trailer(videos) == "https://www.youtube.com/watch?v=abc"

    def test_should_prefer_trailer_over_teaser(self) -> None:
        videos: dict[str, Any] = {
            "results": [
                {"site": "YouTube", "type": "Teaser", "key": "teaser", "official": True},
                {"site": "YouTube", "type": "Trailer", "key": "trailer", "official": False},
            ],
        }
        assert TmdbClient._parse_trailer(videos) == "https://www.youtube.com/watch?v=trailer"

    def test_should_prefer_official_trailer(self) -> None:
        videos: dict[str, Any] = {
            "results": [
                {"site": "YouTube", "type": "Trailer", "key": "unofficial", "official": False},
                {"site": "YouTube", "type": "Trailer", "key": "official", "official": True},
            ],
        }
        assert TmdbClient._parse_trailer(videos) == "https://www.youtube.com/watch?v=official"

    def test_should_skip_non_youtube(self) -> None:
        videos: dict[str, Any] = {
            "results": [
                {"site": "Vimeo", "type": "Trailer", "key": "xyz", "official": True},
            ],
        }
        assert TmdbClient._parse_trailer(videos) is None

    def test_should_return_none_when_empty(self) -> None:
        assert TmdbClient._parse_trailer({"results": []}) is None

    def test_should_handle_invalid_results_type(self) -> None:
        assert TmdbClient._parse_trailer({"results": "bad"}) is None

    def test_should_skip_videos_without_key(self) -> None:
        videos: dict[str, Any] = {
            "results": [
                {"site": "YouTube", "type": "Trailer", "key": "", "official": True},
            ],
        }
        assert TmdbClient._parse_trailer(videos) is None


@pytest.mark.unit
class TestParseCast:
    """Tests for _parse_cast."""

    def test_should_sort_by_order(self) -> None:
        client = _make_client()
        cast_data: list[dict[str, object]] = [
            {"name": "Second", "character": "B", "order": 1, "id": 2},
            {"name": "First", "character": "A", "order": 0, "id": 1},
        ]

        result = client._parse_cast(cast_data)

        assert result[0].name == "First"
        assert result[1].name == "Second"

    def test_should_limit_to_max_cast(self) -> None:
        client = _make_client()
        cast_data: list[dict[str, object]] = [
            {"name": f"Actor{i}", "character": f"Char{i}", "order": i, "id": i} for i in range(25)
        ]

        result = client._parse_cast(cast_data)

        assert len(result) == 15

    def test_should_skip_entries_without_name(self) -> None:
        client = _make_client()
        cast_data: list[dict[str, object]] = [
            {"character": "A", "order": 0, "id": 1},
            {"name": "Real Actor", "character": "B", "order": 1, "id": 2},
        ]

        result = client._parse_cast(cast_data)

        assert len(result) == 1
        assert result[0].name == "Real Actor"

    def test_should_use_character_as_role(self) -> None:
        client = _make_client()
        cast_data: list[dict[str, object]] = [
            {"name": "Actor", "character": "Cobb", "order": 0, "id": 1},
        ]

        result = client._parse_cast(cast_data)

        assert result[0].role == "Cobb"

    def test_should_return_empty_for_no_cast(self) -> None:
        client = _make_client()
        assert client._parse_cast([]) == []


@pytest.mark.unit
class TestParseCrew:
    """Tests for _parse_crew."""

    def test_should_separate_directors_and_writers(self) -> None:
        client = _make_client()
        crew: list[dict[str, object]] = [
            {"name": "Director One", "job": "Director", "department": "Directing", "id": 1},
            {"name": "Writer One", "job": "Writer", "department": "Writing", "id": 2},
        ]

        directors, writers = client._parse_crew(crew)

        assert len(directors) == 1
        assert directors[0].name == "Director One"
        assert len(writers) == 1
        assert writers[0].name == "Writer One"

    def test_should_dedupe_by_name(self) -> None:
        client = _make_client()
        crew: list[dict[str, object]] = [
            {"name": "Same Person", "job": "Director", "department": "Directing", "id": 1},
            {"name": "Same Person", "job": "Director", "department": "Directing", "id": 1},
        ]

        directors, _ = client._parse_crew(crew)

        assert len(directors) == 1

    def test_should_skip_non_director_non_writer(self) -> None:
        client = _make_client()
        crew: list[dict[str, object]] = [
            {"name": "Producer", "job": "Producer", "department": "Production", "id": 1},
        ]

        directors, writers = client._parse_crew(crew)

        assert directors == []
        assert writers == []

    def test_should_skip_entries_without_name(self) -> None:
        client = _make_client()
        crew: list[dict[str, object]] = [
            {"job": "Director", "department": "Directing", "id": 1},
        ]

        directors, _ = client._parse_crew(crew)

        assert directors == []


@pytest.mark.unit
class TestSearchMovie:
    """Tests for search_movie."""

    @pytest.mark.asyncio
    async def test_should_return_metadata_for_match(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data={"results": [{"id": 27205}]}),
                _build_response(json_data=_movie_details()),
            ]
        )

        result = await client.search_movie("Inception", 2010)

        assert result is not None
        assert result.title == "Inception"
        assert result.tmdb_id == 27205
        assert result.year == 2010

    @pytest.mark.asyncio
    async def test_should_return_none_when_no_results(self) -> None:
        client = _make_client(get_responses=_build_response(json_data={"results": []}))

        result = await client.search_movie("Nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_should_use_first_result_when_multiple(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data={"results": [{"id": 100}, {"id": 200}]}),
                _build_response(json_data=_movie_details(tmdb_id=100)),
            ]
        )

        result = await client.search_movie("Test")

        assert result is not None
        assert result.tmdb_id == 100


@pytest.mark.unit
class TestSearchSeries:
    """Tests for search_series."""

    @pytest.mark.asyncio
    async def test_should_return_metadata_for_match(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data={"results": [{"id": 1396}]}),
                _build_response(json_data=_series_details()),
                _build_response(json_data=_season_details()),
            ]
        )

        result = await client.search_series("Breaking Bad", 2008)

        assert result is not None
        assert result.title == "Breaking Bad"
        assert result.tmdb_id == 1396
        assert result.year == 2008

    @pytest.mark.asyncio
    async def test_should_return_none_when_no_results(self) -> None:
        client = _make_client(get_responses=_build_response(json_data={"results": []}))

        result = await client.search_series("Nonexistent")

        assert result is None


@pytest.mark.unit
class TestGetMovieById:
    """Tests for get_movie_by_id."""

    @pytest.mark.asyncio
    async def test_should_fetch_by_id(self) -> None:
        client = _make_client(get_responses=_build_response(json_data=_movie_details()))

        result = await client.get_movie_by_id(27205)

        assert result is not None
        assert result.tmdb_id == 27205

    @pytest.mark.asyncio
    async def test_should_return_none_on_404(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=404))

        result = await client.get_movie_by_id(99999999)

        assert result is None


@pytest.mark.unit
class TestGetSeriesById:
    """Tests for get_series_by_id."""

    @pytest.mark.asyncio
    async def test_should_fetch_by_id(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data=_series_details()),
                _build_response(json_data=_season_details()),
            ]
        )

        result = await client.get_series_by_id(1396)

        assert result is not None
        assert result.tmdb_id == 1396
        assert len(result.seasons) == 1

    @pytest.mark.asyncio
    async def test_should_return_none_on_404(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=404))

        result = await client.get_series_by_id(99999999)

        assert result is None


@pytest.mark.unit
class TestGetMovieLocalized:
    """Tests for get_movie_localized."""

    @pytest.mark.asyncio
    async def test_should_merge_en_and_pt_br(self) -> None:
        pt_data = {
            "title": "A Origem",
            "overview": "Sinopse em português.",
            "genres": [{"name": "Ficção Científica"}],
        }
        # Logos now come bundled in the details response via
        # ``append_to_response=images`` — no separate ``/images`` call.
        client = _make_client(
            get_responses=[
                _build_response(json_data=_movie_details()),  # English details (with images)
                _build_response(json_data=pt_data),  # pt-BR details (with images)
            ]
        )

        result = await client.get_movie_localized(27205)

        assert result is not None
        assert result.title == "Inception"  # English primary
        assert "pt-BR" in result.localized
        assert result.localized["pt-BR"].title == "A Origem"

    @pytest.mark.asyncio
    async def test_should_return_en_only_when_pt_fails(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data=_movie_details()),  # English details
                _build_response(status_code=404),  # pt-BR details (fails)
            ]
        )

        result = await client.get_movie_localized(27205)

        assert result is not None
        assert result.title == "Inception"
        assert result.localized == {}

    @pytest.mark.asyncio
    async def test_should_return_none_when_en_fetch_fails(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=404))

        result = await client.get_movie_localized(99999999)

        assert result is None


@pytest.mark.unit
class TestGetSeriesLocalized:
    """Tests for get_series_localized."""

    @pytest.mark.asyncio
    async def test_should_merge_en_and_pt_br(self) -> None:
        pt_data = {
            "name": "Breaking Bad BR",
            "overview": "Série brasileira localizada.",
            "genres": [{"name": "Drama BR"}],
        }
        # Logos come bundled in details now — no extra ``/images`` calls.
        client = _make_client(
            get_responses=[
                _build_response(json_data=_series_details()),  # series details (with images)
                _build_response(json_data=_season_details()),  # season fetch
                _build_response(json_data=pt_data),  # pt-BR details (with images)
            ]
        )

        result = await client.get_series_localized(1396)

        assert result is not None
        assert "pt-BR" in result.localized
        assert result.localized["pt-BR"].synopsis == "Série brasileira localizada."

    @pytest.mark.asyncio
    async def test_should_return_en_only_when_pt_fails(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data=_series_details()),  # series details
                _build_response(json_data=_season_details()),  # season fetch
                _build_response(status_code=404),  # pt-BR details (fails)
            ]
        )

        result = await client.get_series_localized(1396)

        assert result is not None
        assert result.localized == {}


@pytest.mark.unit
class TestPickBestLogoUrl:
    """Priority order for the ``_pick_best_logo_url`` parser.

    Pure-function tests — no HTTP. The fetcher is now baked into
    ``_fetch_*_details`` via ``append_to_response=images`` and the
    parser only operates on the returned ``logos`` array.
    """

    def _client(self) -> TmdbClient:
        return TmdbClient(api_key="test-key")

    def test_prefers_exact_language_match(self) -> None:
        url = self._client()._pick_best_logo_url(
            [
                {"iso_639_1": "en", "file_path": "/en.png"},
                {"iso_639_1": "pt-BR", "file_path": "/ptbr.png"},
                {"iso_639_1": None, "file_path": "/neutral.png"},
            ],
            "pt-BR",
        )
        assert url is not None
        assert url.endswith("/ptbr.png")

    def test_falls_back_to_base_language(self) -> None:
        # Search for ``pt-PT`` should fall back to the ``pt-BR`` logo
        # (same base ``pt``) when no exact match exists, before
        # English or language-neutral.
        url = self._client()._pick_best_logo_url(
            [
                {"iso_639_1": "en", "file_path": "/en.png"},
                {"iso_639_1": "pt-BR", "file_path": "/ptbr.png"},
            ],
            "pt-PT",
        )
        assert url is not None
        assert url.endswith("/ptbr.png")

    def test_falls_back_to_english(self) -> None:
        url = self._client()._pick_best_logo_url(
            [
                {"iso_639_1": "fr", "file_path": "/fr.png"},
                {"iso_639_1": "en", "file_path": "/en.png"},
            ],
            "pt-BR",
        )
        assert url is not None
        assert url.endswith("/en.png")

    def test_falls_back_to_language_neutral(self) -> None:
        url = self._client()._pick_best_logo_url(
            [
                {"iso_639_1": "ja", "file_path": "/ja.png"},
                {"iso_639_1": None, "file_path": "/neutral.png"},
            ],
            "pt-BR",
        )
        assert url is not None
        assert url.endswith("/neutral.png")

    def test_falls_back_to_first_logo_when_nothing_else_matches(self) -> None:
        url = self._client()._pick_best_logo_url(
            [{"iso_639_1": "ja", "file_path": "/ja.png"}],
            "pt-BR",
        )
        assert url is not None
        assert url.endswith("/ja.png")

    def test_returns_none_when_list_empty(self) -> None:
        assert self._client()._pick_best_logo_url([], "pt-BR") is None

    def test_returns_none_when_list_is_none(self) -> None:
        assert self._client()._pick_best_logo_url(None, "pt-BR") is None


@pytest.mark.unit
class TestFetchMovieDetails:
    """Tests for _fetch_movie_details field mapping."""

    @pytest.mark.asyncio
    async def test_should_extract_year_from_release_date(self) -> None:
        client = _make_client(get_responses=_build_response(json_data=_movie_details()))

        result = await client._fetch_movie_details(27205)

        assert result is not None
        assert result.year == 2010

    @pytest.mark.asyncio
    async def test_should_convert_runtime_minutes_to_seconds(self) -> None:
        client = _make_client(get_responses=_build_response(json_data=_movie_details()))

        result = await client._fetch_movie_details(27205)

        assert result is not None
        assert result.duration_seconds == 148 * 60

    @pytest.mark.asyncio
    async def test_should_build_full_image_urls(self) -> None:
        client = _make_client(get_responses=_build_response(json_data=_movie_details()))

        result = await client._fetch_movie_details(27205)

        assert result is not None
        assert result.poster_url == "https://image.tmdb.org/t/p/original/poster.jpg"
        assert result.backdrop_url == "https://image.tmdb.org/t/p/original/backdrop.jpg"

    @pytest.mark.asyncio
    async def test_should_return_none_on_404(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=404))

        result = await client._fetch_movie_details(99999999)

        assert result is None

    @pytest.mark.asyncio
    async def test_should_handle_missing_optional_fields(self) -> None:
        minimal_data = {
            "id": 1,
            "title": "Minimal",
        }
        client = _make_client(get_responses=_build_response(json_data=minimal_data))

        result = await client._fetch_movie_details(1)

        assert result is not None
        assert result.title == "Minimal"
        assert result.year is None
        assert result.poster_url is None


@pytest.mark.unit
class TestFetchSeriesDetails:
    """Tests for _fetch_series_details."""

    @pytest.mark.asyncio
    async def test_should_extract_start_and_end_year(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data=_series_details()),
                _build_response(json_data=_season_details()),
            ]
        )

        result = await client._fetch_series_details(1396)

        assert result is not None
        assert result.year == 2008
        assert result.end_year == 2013

    @pytest.mark.asyncio
    async def test_should_not_set_end_year_for_running_series(self) -> None:
        data = _series_details()
        data["status"] = "Returning Series"
        client = _make_client(
            get_responses=[
                _build_response(json_data=data),
                _build_response(json_data=_season_details()),
            ]
        )

        result = await client._fetch_series_details(1396)

        assert result is not None
        assert result.end_year is None

    @pytest.mark.asyncio
    async def test_should_fetch_seasons(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data=_series_details()),
                _build_response(json_data=_season_details()),
            ]
        )

        result = await client._fetch_series_details(1396)

        assert result is not None
        assert len(result.seasons) == 1
        assert result.seasons[0].season_number == 1
        assert len(result.seasons[0].episodes) == 1

    @pytest.mark.asyncio
    async def test_should_return_none_on_404(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=404))

        result = await client._fetch_series_details(99999999)

        assert result is None


@pytest.mark.unit
class TestFetchSeason:
    """Tests for _fetch_season."""

    @pytest.mark.asyncio
    async def test_should_fetch_season_with_episodes(self) -> None:
        client = _make_client(get_responses=_build_response(json_data=_season_details()))

        result = await client._fetch_season(1396, 1)

        assert result is not None
        assert result.season_number == 1
        assert len(result.episodes) == 1
        assert result.episodes[0].title == "Pilot"

    @pytest.mark.asyncio
    async def test_should_convert_episode_runtime_to_seconds(self) -> None:
        client = _make_client(get_responses=_build_response(json_data=_season_details()))

        result = await client._fetch_season(1396, 1)

        assert result is not None
        assert result.episodes[0].duration_seconds == 58 * 60

    @pytest.mark.asyncio
    async def test_should_return_none_on_404(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=404))

        result = await client._fetch_season(1396, 99)

        assert result is None
