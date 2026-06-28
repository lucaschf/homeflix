"""Tests for TmdbClient."""

import itertools
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.building_blocks.infrastructure.errors import (
    GatewayBadResponseException,
    GatewayException,
    GatewayRateLimitException,
    GatewayTimeoutException,
    GatewayUnavailableException,
)
from src.modules.media.domain.value_objects import ContentRating
from src.modules.media.infrastructure.metadata.tmdb_client import (
    TmdbClient,
    _parse_retry_after,
    _safe_int,
)
from src.shared_kernel.value_objects import MediaType


def _build_response(
    status_code: int = 200,
    json_data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Build a mocked httpx Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.headers = headers or {}
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
    """Tests for _parse_content_rating (config-driven jurisdiction)."""

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
        assert _make_client()._parse_content_rating(data) == ContentRating("14")

    def test_should_fallback_to_us(self) -> None:
        data: dict[str, Any] = {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [{"certification": "PG-13"}],
                },
            ],
        }
        assert _make_client()._parse_content_rating(data) == ContentRating("PG-13")

    def test_should_return_none_when_empty(self) -> None:
        assert _make_client()._parse_content_rating({"results": []}) is None

    def test_should_return_none_when_missing_key(self) -> None:
        assert _make_client()._parse_content_rating({}) is None

    def test_should_handle_invalid_results_type(self) -> None:
        assert _make_client()._parse_content_rating({"results": "bad"}) is None

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
        assert _make_client()._parse_content_rating(data) == ContentRating("R")

    def test_jurisdiction_order_is_config_driven(self) -> None:
        # A newly supported locale's certification body is respected
        # without editing the gateway: es-ES → ES wins over the US
        # fallback (vs the old hardcoded BR-then-US).
        client = TmdbClient(api_key="test-key", supported_locales=("en", "es-ES"))
        data: dict[str, Any] = {
            "results": [
                {"iso_3166_1": "US", "release_dates": [{"certification": "PG-13"}]},
                {"iso_3166_1": "ES", "release_dates": [{"certification": "12"}]},
            ],
        }
        assert client._parse_content_rating(data) == ContentRating("12")

    def test_returns_none_when_no_preferred_country_matches(self) -> None:
        # Default prefs [BR, US]; payload only has FR → nothing selected.
        data: dict[str, Any] = {
            "results": [
                {"iso_3166_1": "FR", "release_dates": [{"certification": "12"}]},
            ],
        }
        assert _make_client()._parse_content_rating(data) is None

    def test_region_parsed_by_content_not_position(self) -> None:
        # A script subtag (zh-Hant-TW) must not be mistaken for the region:
        # TW is the region, so a TW certification is selected over US.
        client = TmdbClient(api_key="test-key", supported_locales=("en", "zh-Hant-TW"))
        data: dict[str, Any] = {
            "results": [
                {"iso_3166_1": "US", "release_dates": [{"certification": "PG-13"}]},
                {"iso_3166_1": "TW", "release_dates": [{"certification": "0+"}]},
            ],
        }
        assert client._parse_content_rating(data) == ContentRating("0+")


@pytest.mark.unit
class TestParseSeriesContentRating:
    """Tests for _parse_series_content_rating."""

    def test_jurisdiction_order_is_config_driven(self) -> None:
        # Series selection is config-driven too (parity with movie): a
        # configured locale's region wins over the US fallback.
        client = TmdbClient(api_key="test-key", supported_locales=("en", "es-ES"))
        data: dict[str, Any] = {
            "results": [
                {"iso_3166_1": "US", "rating": "TV-14"},
                {"iso_3166_1": "ES", "rating": "12"},
            ],
        }
        assert client._parse_series_content_rating(data) == ContentRating("12")

    def test_should_prefer_br(self) -> None:
        data: dict[str, Any] = {
            "results": [
                {"iso_3166_1": "US", "rating": "TV-MA"},
                {"iso_3166_1": "BR", "rating": "18"},
            ],
        }
        assert _make_client()._parse_series_content_rating(data) == ContentRating("18")

    def test_should_fallback_to_us(self) -> None:
        data: dict[str, Any] = {"results": [{"iso_3166_1": "US", "rating": "TV-14"}]}
        assert _make_client()._parse_series_content_rating(data) == ContentRating("TV-14")

    def test_should_return_none_when_empty(self) -> None:
        assert _make_client()._parse_series_content_rating({}) is None

    def test_should_handle_invalid_results_type(self) -> None:
        assert _make_client()._parse_series_content_rating({"results": "bad"}) is None


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
class TestSummaryByIdErrorHandling:
    """``get_*_summary_by_id`` separates not-found from provider failure.

    A genuine 404 (the id isn't that media kind) returns ``None``; any
    other failure (HTTP status or transport/connection) raises so a
    transient outage doesn't masquerade as "no such id".
    """

    @pytest.mark.asyncio
    async def test_movie_summary_returns_none_on_404(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=404))

        assert await client.get_movie_summary_by_id(123) is None

    @pytest.mark.asyncio
    async def test_series_summary_returns_none_on_404(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=404))

        assert await client.get_series_summary_by_id(123) is None

    @pytest.mark.asyncio
    async def test_movie_summary_raises_on_server_error(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=500))

        with pytest.raises(GatewayUnavailableException):
            await client.get_movie_summary_by_id(123)

    @pytest.mark.asyncio
    async def test_series_summary_raises_on_server_error(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=500))

        with pytest.raises(GatewayUnavailableException):
            await client.get_series_summary_by_id(123)

    @pytest.mark.asyncio
    async def test_movie_summary_returns_candidate_on_200(self) -> None:
        client = _make_client(get_responses=_build_response(json_data=_movie_details()))

        result = await client.get_movie_summary_by_id(27205)

        assert result is not None
        assert result.tmdb_id == 27205

    @pytest.mark.asyncio
    async def test_series_summary_returns_candidate_on_200(self) -> None:
        client = _make_client(get_responses=_build_response(json_data=_series_details()))

        result = await client.get_series_summary_by_id(1396)

        assert result is not None
        assert result.tmdb_id == 1396

    @pytest.mark.asyncio
    async def test_movie_summary_propagates_connection_error(self) -> None:
        client = _make_client()
        client._client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with pytest.raises(GatewayUnavailableException):
            await client.get_movie_summary_by_id(123)

    @pytest.mark.asyncio
    async def test_series_summary_propagates_connection_error(self) -> None:
        client = _make_client()
        client._client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with pytest.raises(GatewayUnavailableException):
            await client.get_series_summary_by_id(123)


@pytest.mark.unit
class TestParseRetryAfter:
    """``_parse_retry_after`` reads the delta-seconds form, ignores the rest."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("30", 30),
            ("0", 0),
            ("  12 ", 12),
            (None, None),
            ("abc", None),
            ("-5", None),
            ("Wed, 21 Oct 2025 07:28:00 GMT", None),
        ],
    )
    def test_parse(self, value: str | None, expected: int | None) -> None:
        assert _parse_retry_after(value) == expected


@pytest.mark.unit
class TestGatewayErrorTranslation:
    """The TMDB ACL wraps every provider failure as a GatewayException subtype.

    Card A: a provider outage must surface as 429/502/503/504 — never a
    generic 500 — and transport errors must not leak raw ``httpx`` types
    past the adapter boundary.
    """

    @pytest.mark.asyncio
    async def test_timeout_becomes_gateway_timeout(self) -> None:
        client = _make_client()
        client._client.get = AsyncMock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(GatewayTimeoutException):
            await client.get_movie_summary_by_id(1)

    @pytest.mark.asyncio
    async def test_connect_error_becomes_gateway_unavailable(self) -> None:
        client = _make_client()
        client._client.get = AsyncMock(side_effect=httpx.ConnectError("down"))

        with pytest.raises(GatewayUnavailableException):
            await client.get_movie_summary_by_id(1)

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (429, GatewayRateLimitException),
            (503, GatewayUnavailableException),
            (504, GatewayTimeoutException),
            (502, GatewayBadResponseException),
            (500, GatewayUnavailableException),
            (401, GatewayException),
            (400, GatewayException),
        ],
    )
    def test_status_maps_to_subtype(self, status: int, expected: type[GatewayException]) -> None:
        with pytest.raises(GatewayException) as exc_info:
            TmdbClient._raise_for_status(_build_response(status_code=status))
        # Exact type — base GatewayException for 4xx, never a subtype.
        assert type(exc_info.value) is expected

    def test_success_status_does_not_raise(self) -> None:
        TmdbClient._raise_for_status(_build_response(status_code=200))

    def test_rate_limit_reads_retry_after_header(self) -> None:
        resp = _build_response(status_code=429, headers={"Retry-After": "42"})

        with pytest.raises(GatewayRateLimitException) as exc_info:
            TmdbClient._raise_for_status(resp)

        assert exc_info.value.retry_after_seconds == 42

    def test_rate_limit_defaults_retry_after_when_header_missing(self) -> None:
        with pytest.raises(GatewayRateLimitException) as exc_info:
            TmdbClient._raise_for_status(_build_response(status_code=429))

        assert exc_info.value.retry_after_seconds == 60

    @pytest.mark.asyncio
    async def test_best_effort_methods_still_degrade_on_gateway_error(self) -> None:
        client = _make_client()
        client._client.get = AsyncMock(side_effect=httpx.ConnectError("down"))

        # These paths intentionally swallow provider failures so the UI
        # degrades gracefully — the wrapped GatewayException must still be
        # caught, not propagate.
        assert await client.get_collection(10) is None
        assert await client.get_person(287) is None
        assert await client.get_movie_recommendations(1) == []

    @pytest.mark.asyncio
    async def test_localized_overlay_skips_on_transport_error(self) -> None:
        client = _make_client()
        client._client.get = AsyncMock(side_effect=httpx.ConnectError("down"))

        # A localized overlay is best-effort — a wrapped transport error
        # drops just that locale rather than aborting enrichment.
        assert await client._fetch_movie_localized_fields(1, "pt-BR") is None
        assert await client._fetch_series_localized_fields(1, "pt-BR") is None

    @pytest.mark.asyncio
    async def test_season_overlay_skips_but_base_propagates_on_transport_error(self) -> None:
        client = _make_client()
        client._client.get = AsyncMock(side_effect=httpx.ConnectError("down"))

        # An overlay locale failing is dropped (the concurrent fan-out
        # must not abort)...
        assert await client._fetch_season_payload(1, 1, "pt-BR") is None
        # ...but the English base failing is fatal and propagates.
        with pytest.raises(GatewayUnavailableException):
            await client._fetch_season_payload(1, 1, None)


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
                _build_response(
                    json_data={"results": [{"id": 27205, "release_date": "2010-07-16"}]}
                ),
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
    async def test_should_use_first_result_when_no_year_hint(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data={"results": [{"id": 100}, {"id": 200}]}),
                _build_response(json_data=_movie_details(tmdb_id=100)),
            ]
        )

        result = await client.search_movie("Test")

        assert result is not None
        assert result.tmdb_id == 100

    @pytest.mark.asyncio
    async def test_should_prefer_year_match_over_first_result(self) -> None:
        """American Gothic-style case for movies: year-correct entry is not
        ranked first by TMDB and must be selected by the year post-filter."""
        client = _make_client(
            get_responses=[
                _build_response(
                    json_data={
                        "results": [
                            {"id": 748230, "release_date": "2024-10-03"},
                            {"id": 555, "release_date": "2016-05-12"},
                        ]
                    }
                ),
                _build_response(json_data=_movie_details(tmdb_id=555)),
            ]
        )

        result = await client.search_movie("Salem's Lot", 2016)

        assert result is not None
        assert result.tmdb_id == 555

    @pytest.mark.asyncio
    async def test_should_return_none_when_no_result_matches_year(self) -> None:
        """Salem's Lot 1979 case: the 1979 entry isn't a movie on TMDB, so
        no movie result matches year=1979. Returns None so the caller can
        retry without the year hint instead of silently picking 2024."""
        client = _make_client(
            get_responses=_build_response(
                json_data={
                    "results": [
                        {"id": 748230, "release_date": "2024-10-03"},
                        {"id": 999, "release_date": "2004-06-04"},
                    ]
                }
            )
        )

        result = await client.search_movie("Salem's Lot", 1979)

        assert result is None

    @pytest.mark.asyncio
    async def test_should_skip_results_with_missing_release_date(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(
                    json_data={
                        "results": [
                            {"id": 100},
                            {"id": 200, "release_date": ""},
                            {"id": 300, "release_date": "2010-07-16"},
                        ]
                    }
                ),
                _build_response(json_data=_movie_details(tmdb_id=300)),
            ]
        )

        result = await client.search_movie("Inception", 2010)

        assert result is not None
        assert result.tmdb_id == 300


@pytest.mark.unit
class TestSearchSeries:
    """Tests for search_series."""

    @pytest.mark.asyncio
    async def test_should_return_metadata_for_match(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(
                    json_data={"results": [{"id": 1396, "first_air_date": "2008-01-20"}]}
                ),
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

    @pytest.mark.asyncio
    async def test_should_prefer_year_match_over_first_result(self) -> None:
        """American Gothic 2016 case: TMDB ranks the more-popular 1995
        series first even when ``first_air_date_year=2016`` is set. The
        post-filter must pick the 2016 entry."""
        client = _make_client(
            get_responses=[
                _build_response(
                    json_data={
                        "results": [
                            {"id": 11366, "first_air_date": "1995-09-22"},
                            {"id": 66718, "first_air_date": "2016-06-22"},
                        ]
                    }
                ),
                _build_response(
                    json_data={**_series_details(), "id": 66718, "name": "American Gothic"}
                ),
                _build_response(json_data=_season_details()),
            ]
        )

        result = await client.search_series("American Gothic", 2016)

        assert result is not None
        assert result.tmdb_id == 66718

    @pytest.mark.asyncio
    async def test_should_return_none_when_no_result_matches_year(self) -> None:
        client = _make_client(
            get_responses=_build_response(
                json_data={
                    "results": [
                        {"id": 11366, "first_air_date": "1995-09-22"},
                        {"id": 9999, "first_air_date": "2004-06-04"},
                    ]
                }
            )
        )

        result = await client.search_series("American Gothic", 2016)

        assert result is None


@pytest.mark.unit
class TestFindMovieCandidates:
    """Tests for ``find_movie_candidates`` — picker-mode raw search."""

    @pytest.mark.asyncio
    async def test_should_return_raw_candidates_without_detail_fetch(self) -> None:
        """A single HTTP call (no per-id detail roundtrip) is the
        whole point of the picker path."""
        client = _make_client(
            get_responses=_build_response(
                json_data={
                    "results": [
                        {
                            "id": 748230,
                            "title": "Salem's Lot",
                            "release_date": "2024-10-03",
                            "overview": "Reboot",
                            "poster_path": "/poster.jpg",
                        },
                    ],
                },
            ),
        )

        result = await client.find_movie_candidates("Salem's Lot", year=2024, limit=5)

        assert len(result) == 1
        assert result[0].tmdb_id == 748230
        assert result[0].media_type == "movie"
        assert result[0].year == 2024
        assert result[0].poster_url == "https://image.tmdb.org/t/p/original/poster.jpg"

    @pytest.mark.asyncio
    async def test_should_truncate_to_limit(self) -> None:
        client = _make_client(
            get_responses=_build_response(
                json_data={
                    "results": [
                        {"id": i, "title": f"M{i}", "release_date": "2020-01-01"} for i in range(10)
                    ],
                },
            ),
        )

        result = await client.find_movie_candidates("M", year=None, limit=3)

        assert [c.tmdb_id for c in result] == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_should_return_empty_when_no_results(self) -> None:
        client = _make_client(get_responses=_build_response(json_data={"results": []}))

        result = await client.find_movie_candidates("Nonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_should_handle_missing_release_date(self) -> None:
        client = _make_client(
            get_responses=_build_response(
                json_data={"results": [{"id": 100, "title": "Unknown Year"}]},
            ),
        )

        result = await client.find_movie_candidates("Unknown Year")

        assert result[0].year is None


@pytest.mark.unit
class TestFindSeriesCandidates:
    """Tests for ``find_series_candidates`` — picker-mode raw search."""

    @pytest.mark.asyncio
    async def test_should_return_raw_candidates_with_tv_media_type(self) -> None:
        client = _make_client(
            get_responses=_build_response(
                json_data={
                    "results": [
                        {
                            "id": 16118,
                            "name": "Salem's Lot",
                            "first_air_date": "1979-11-17",
                            "overview": "Tobe Hooper miniseries",
                            "poster_path": "/sl.jpg",
                        },
                    ],
                },
            ),
        )

        result = await client.find_series_candidates("Salem's Lot", year=1979)

        assert len(result) == 1
        assert result[0].tmdb_id == 16118
        assert result[0].media_type == "tv"
        assert result[0].year == 1979
        assert result[0].title == "Salem's Lot"


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
class TestGetPerson:
    """Tests for ``get_person`` (TMDB ``/person/{id}``)."""

    @pytest.mark.asyncio
    async def test_should_parse_person_payload(self) -> None:
        client = _make_client(
            get_responses=_build_response(
                json_data={
                    "id": 6193,
                    "name": "Leonardo DiCaprio",
                    "biography": "American actor born in 1974.",
                    "birthday": "1974-11-11",
                    "deathday": None,
                    "place_of_birth": "Los Angeles, California, USA",
                    "known_for_department": "Acting",
                    "profile_path": "/leo.jpg",
                }
            )
        )

        result = await client.get_person(6193)

        assert result is not None
        assert result.tmdb_id == 6193
        assert result.name == "Leonardo DiCaprio"
        assert result.biography == "American actor born in 1974."
        assert result.birthday == "1974-11-11"
        assert result.deathday is None
        assert result.place_of_birth == "Los Angeles, California, USA"
        assert result.known_for_department == "Acting"
        # ``profile_path`` is rewritten to a CDN URL by ``_image_url``.
        assert result.profile_path == "https://image.tmdb.org/t/p/original/leo.jpg"

    @pytest.mark.asyncio
    async def test_should_return_none_on_404(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=404))

        result = await client.get_person(99999999)

        assert result is None

    @pytest.mark.asyncio
    async def test_should_return_none_on_network_error(self) -> None:
        # ``HTTPError`` (e.g. timeout, connection reset) collapses to
        # ``None`` so the actor page degrades to a name-only header
        # instead of erroring out.
        client = TmdbClient(api_key="test-key")
        mock_http = MagicMock()
        mock_http.get = AsyncMock(side_effect=httpx.RequestError("boom"))
        client._client = mock_http

        result = await client.get_person(6193)

        assert result is None

    @pytest.mark.asyncio
    async def test_should_return_none_when_payload_missing_id(self) -> None:
        client = _make_client(
            get_responses=_build_response(
                json_data={"name": "Leonardo DiCaprio"},  # no id
            )
        )

        result = await client.get_person(6193)

        assert result is None

    @pytest.mark.asyncio
    async def test_should_collapse_empty_strings_to_none(self) -> None:
        # TMDB returns ``""`` for unknown places of birth on some rows;
        # the parser flattens those to ``None`` so the UI's
        # ``value && <render>`` guards do the right thing.
        client = _make_client(
            get_responses=_build_response(
                json_data={
                    "id": 6193,
                    "name": "Leonardo DiCaprio",
                    "biography": "",
                    "birthday": "",
                    "place_of_birth": "",
                    "known_for_department": "",
                    "profile_path": "",
                }
            )
        )

        result = await client.get_person(6193)

        assert result is not None
        assert result.biography == ""
        assert result.birthday is None
        assert result.place_of_birth is None
        assert result.known_for_department is None
        assert result.profile_path is None

    @pytest.mark.asyncio
    async def test_should_fall_back_to_english_when_localized_bio_is_empty(self) -> None:
        # TMDB has the pt-BR payload but didn't author the bio in pt;
        # the client should fetch English and use only that bio,
        # keeping the rest of the localized fields.
        client = _make_client(
            get_responses=[
                _build_response(
                    json_data={
                        "id": 6193,
                        "name": "Leonardo DiCaprio",
                        "biography": "",
                        "birthday": "1974-11-11",
                        "place_of_birth": "Los Angeles, Califórnia, EUA",
                        "known_for_department": "Acting",
                        "profile_path": "/leo.jpg",
                    },
                ),
                _build_response(
                    json_data={
                        "id": 6193,
                        "name": "Leonardo DiCaprio",
                        "biography": "American actor born in 1974.",
                        "birthday": "1974-11-11",
                        "place_of_birth": "Los Angeles, California, USA",
                        "known_for_department": "Acting",
                        "profile_path": "/leo.jpg",
                    },
                ),
            ]
        )

        result = await client.get_person(6193, language="pt-BR")

        assert result is not None
        assert result.biography == "American actor born in 1974."
        # Localized fields kept — only the empty bio was replaced.
        assert result.place_of_birth == "Los Angeles, Califórnia, EUA"

    @pytest.mark.asyncio
    async def test_should_not_fall_back_when_english_request_returned_empty(self) -> None:
        # English already returned empty — no second call needed; the
        # ``_is_english`` short-circuit avoids burning an HTTP request
        # on a guaranteed no-op.
        client = _make_client(
            get_responses=_build_response(
                json_data={
                    "id": 6193,
                    "name": "Leonardo DiCaprio",
                    "biography": "",
                    "birthday": "1974-11-11",
                },
            )
        )

        result = await client.get_person(6193, language="en-US")

        assert result is not None
        assert result.biography == ""

    @pytest.mark.asyncio
    async def test_should_keep_localized_bio_when_present(self) -> None:
        # When the localized fetch already has a bio, no fallback fires
        # — saves an HTTP round-trip when TMDB has translations.
        client = _make_client(
            get_responses=_build_response(
                json_data={
                    "id": 6193,
                    "name": "Leonardo DiCaprio",
                    "biography": "Ator americano nascido em 1974.",
                },
            )
        )

        result = await client.get_person(6193, language="pt-BR")

        assert result is not None
        assert result.biography == "Ator americano nascido em 1974."


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
        # Series base carries no seasons here so the flow stays focused on
        # series-level localization (season fan-out is covered separately).
        client = _make_client(
            get_responses=[
                _build_response(json_data={**_series_details(), "seasons": []}),  # series base
                _build_response(json_data=pt_data),  # series-level pt-BR overlay
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
                _build_response(json_data={**_series_details(), "seasons": []}),  # series base
                _build_response(status_code=404),  # series-level pt-BR overlay (fails)
            ]
        )

        result = await client.get_series_localized(1396)

        assert result is not None
        assert result.localized == {}


@pytest.mark.unit
class TestLocalizedSupportedLocales:
    """``get_*_localized`` overlays exactly the configured non-English locales."""

    @staticmethod
    def _client_with_locales(
        locales: tuple[str, ...], get_responses: list[MagicMock]
    ) -> TmdbClient:
        client = TmdbClient(api_key="test-key", supported_locales=locales)
        mock_http = MagicMock()
        empty_logos_tail = itertools.repeat(_build_response(json_data={"logos": []}))
        mock_http.get = AsyncMock(side_effect=itertools.chain(get_responses, empty_logos_tail))
        client._client = mock_http
        return client

    @pytest.mark.asyncio
    async def test_movie_overlays_every_non_english_locale(self) -> None:
        client = self._client_with_locales(
            ("en", "pt-BR", "es-ES"),
            [
                _build_response(json_data=_movie_details()),  # English base
                _build_response(json_data={"title": "A Origem", "overview": "PT"}),  # pt-BR
                _build_response(json_data={"title": "El Origen", "overview": "ES"}),  # es-ES
            ],
        )

        result = await client.get_movie_localized(27205)

        assert result is not None
        assert set(result.localized) == {"pt-BR", "es-ES"}
        assert result.localized["pt-BR"].title == "A Origem"
        assert result.localized["es-ES"].title == "El Origen"

    @pytest.mark.asyncio
    async def test_movie_localizes_poster_and_backdrop_per_locale(self) -> None:
        client = self._client_with_locales(
            ("en", "pt-BR"),
            [
                _build_response(json_data=_movie_details()),  # English base
                _build_response(
                    json_data={
                        "title": "A Origem",
                        "poster_path": "/ptbr-poster.jpg",
                        "backdrop_path": "/ptbr-backdrop.jpg",
                    }
                ),
            ],
        )

        result = await client.get_movie_localized(27205)

        assert result is not None
        # English base keeps its global artwork...
        assert result.poster_url == "https://image.tmdb.org/t/p/original/poster.jpg"
        # ...while the pt-BR overlay carries the localized artwork.
        fields = result.localized["pt-BR"]
        assert fields.poster_url == "https://image.tmdb.org/t/p/original/ptbr-poster.jpg"
        assert fields.backdrop_url == "https://image.tmdb.org/t/p/original/ptbr-backdrop.jpg"

    @pytest.mark.asyncio
    async def test_movie_skips_failed_locale_but_keeps_others(self) -> None:
        client = self._client_with_locales(
            ("en", "pt-BR", "es-ES"),
            [
                _build_response(json_data=_movie_details()),  # English base
                _build_response(status_code=404),  # pt-BR fails
                _build_response(json_data={"title": "El Origen", "overview": "ES"}),  # es-ES
            ],
        )

        result = await client.get_movie_localized(27205)

        assert result is not None
        assert set(result.localized) == {"es-ES"}

    @pytest.mark.asyncio
    async def test_english_only_config_produces_no_overlays(self) -> None:
        client = self._client_with_locales(
            ("en",),
            [_build_response(json_data=_movie_details())],  # English base only
        )

        result = await client.get_movie_localized(27205)

        assert result is not None
        assert result.localized == {}

    @pytest.mark.asyncio
    async def test_series_overlays_every_non_english_locale(self) -> None:
        # Seasonless series base keeps the flow on series-level overlays.
        client = self._client_with_locales(
            ("en", "pt-BR", "es-ES"),
            [
                _build_response(json_data={**_series_details(), "seasons": []}),  # series base
                _build_response(json_data={"name": "BB BR", "overview": "PT"}),  # pt-BR overlay
                _build_response(json_data={"name": "BB ES", "overview": "ES"}),  # es-ES overlay
            ],
        )

        result = await client.get_series_localized(1396)

        assert result is not None
        assert set(result.localized) == {"pt-BR", "es-ES"}
        assert result.localized["es-ES"].synopsis == "ES"


@pytest.mark.unit
class TestGetTranslatedTitles:
    """``get_translated_titles`` maps TMDB ``/translations`` to supported locales."""

    _PAYLOAD: ClassVar[dict[str, Any]] = {
        "translations": [
            {"iso_639_1": "en", "iso_3166_1": "US", "data": {"title": "Alien", "name": "Alien"}},
            {
                "iso_639_1": "pt",
                "iso_3166_1": "BR",
                "data": {"title": "Alien, o Oitavo Passageiro", "name": "Alien BR"},
            },
            {
                "iso_639_1": "pt",
                "iso_3166_1": "PT",
                "data": {"title": "Alien, o 8º Passageiro", "name": "Alien PT"},
            },
        ]
    }

    @pytest.mark.asyncio
    async def test_movie_maps_supported_locales(self) -> None:
        client = _make_client(get_responses=_build_response(json_data=self._PAYLOAD))

        titles = await client.get_translated_titles(348, MediaType.MOVIE)

        assert titles == {"en": "Alien", "pt-BR": "Alien, o Oitavo Passageiro"}

    @pytest.mark.asyncio
    async def test_series_uses_name_key(self) -> None:
        client = _make_client(get_responses=_build_response(json_data=self._PAYLOAD))

        titles = await client.get_translated_titles(1396, MediaType.SERIES)

        assert titles == {"en": "Alien", "pt-BR": "Alien BR"}

    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self) -> None:
        client = _make_client(get_responses=_build_response(status_code=500))

        assert await client.get_translated_titles(348, MediaType.MOVIE) == {}

    @pytest.mark.asyncio
    async def test_omits_locales_without_translation(self) -> None:
        client = TmdbClient(api_key="test-key", supported_locales=("en", "pt-BR", "es-ES"))
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=_build_response(json_data=self._PAYLOAD))
        client._client = mock_http

        titles = await client.get_translated_titles(348, MediaType.MOVIE)

        # No Spanish entry in the payload → es-ES is omitted.
        assert "es-ES" not in titles
        assert set(titles) == {"en", "pt-BR"}


@pytest.mark.unit
class TestSeasonEpisodeLocalization:
    """``_fetch_season`` overlays per-locale season + episode title/synopsis."""

    @pytest.mark.asyncio
    async def test_season_and_episode_carry_localized_text(self) -> None:
        season_ptbr = {
            "name": "Temporada 1",
            "overview": "Visão geral em português.",
            "episodes": [
                {"episode_number": 1, "name": "Piloto", "overview": "Walter começa."},
            ],
        }
        client = _make_client(
            get_responses=[
                _build_response(json_data=_series_details()),  # series base (1 season)
                _build_response(json_data=_season_details()),  # season English base
                _build_response(json_data=season_ptbr),  # season pt-BR overlay
                _build_response(json_data={"name": "BB BR"}),  # series-level pt-BR overlay
            ]
        )

        result = await client.get_series_localized(1396)

        assert result is not None
        season = result.seasons[0]
        assert season.localized["pt-BR"].title == "Temporada 1"
        assert season.localized["pt-BR"].synopsis == "Visão geral em português."
        episode = season.episodes[0]
        assert episode.title == "Pilot"  # English base preserved
        assert episode.localized["pt-BR"].title == "Piloto"
        assert episode.localized["pt-BR"].synopsis == "Walter começa."

    @pytest.mark.asyncio
    async def test_season_locale_overlay_failure_is_skipped(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data=_series_details()),  # series base
                _build_response(json_data=_season_details()),  # season English base
                _build_response(status_code=500),  # season pt-BR overlay fails
                _build_response(json_data={"name": "BB BR"}),  # series-level pt-BR overlay
            ]
        )

        result = await client.get_series_localized(1396)

        assert result is not None
        season = result.seasons[0]
        assert season.localized == {}
        assert season.episodes[0].localized == {}


@pytest.mark.unit
class TestGetMovieRecommendations:
    """``get_movie_recommendations`` — collection + ML / heuristic merge.

    Call sequence in production is:

    1. ``/movie/{id}`` to read ``belongs_to_collection`` (always).
    2. ``/collection/{id}`` for the franchise siblings (only when
       ``belongs_to_collection`` is set).
    3. ``/movie/{id}/recommendations`` for ML-based recs.
    4. ``/movie/{id}/similar`` only when recommendations is empty.

    Tests provide a mock per call in that order.
    """

    @pytest.mark.asyncio
    async def test_returns_recommended_ids_in_order(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data={}),  # /movie/{id} — no collection
                _build_response(  # /recommendations
                    json_data={"results": [{"id": 27205}, {"id": 1422}, {"id": 524434}]},
                ),
            ],
        )

        ids = await client.get_movie_recommendations(155)

        assert ids == [27205, 1422, 524434]

    @pytest.mark.asyncio
    async def test_falls_back_to_similar_when_recommendations_empty(self) -> None:
        # ``/recommendations`` is sparse for less popular movies;
        # ``/similar`` is heuristic and almost always populated.
        client = _make_client(
            get_responses=[
                _build_response(json_data={}),  # /movie/{id} — no collection
                _build_response(json_data={"results": []}),  # /recommendations
                _build_response(  # /similar
                    json_data={"results": [{"id": 99}, {"id": 100}]},
                ),
            ],
        )

        ids = await client.get_movie_recommendations(42)

        assert ids == [99, 100]

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_sources_empty(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data={}),  # /movie/{id}
                _build_response(json_data={"results": []}),  # /recommendations
                _build_response(json_data={"results": []}),  # /similar
            ],
        )

        ids = await client.get_movie_recommendations(42)

        assert ids == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(status_code=500),  # /movie/{id}
                _build_response(status_code=500),  # /recommendations
                _build_response(status_code=500),  # /similar
            ],
        )

        ids = await client.get_movie_recommendations(42)

        assert ids == []

    @pytest.mark.asyncio
    async def test_skips_non_int_ids_in_payload(self) -> None:
        # Defensive: a malformed TMDB row shouldn't crash the parser.
        client = _make_client(
            get_responses=[
                _build_response(json_data={}),  # /movie/{id}
                _build_response(  # /recommendations
                    json_data={
                        "results": [
                            {"id": 1},
                            {"id": "not-an-int"},
                            {"name": "no id here"},
                            {"id": 2},
                        ]
                    },
                ),
            ],
        )

        ids = await client.get_movie_recommendations(155)

        assert ids == [1, 2]

    @pytest.mark.asyncio
    async def test_includes_collection_siblings_first(self) -> None:
        # Creepshow-style: TMDB's ML rarely surfaces sequels for
        # older titles, but the franchise's collection always lists
        # them. Collection ids come first in the merged result and
        # the input movie itself is skipped.
        client = _make_client(
            get_responses=[
                _build_response(  # /movie/12552
                    json_data={
                        "belongs_to_collection": {
                            "id": 91349,
                            "name": "Creepshow Collection",
                        },
                    },
                ),
                _build_response(  # /collection/91349
                    json_data={
                        "parts": [
                            {"id": 12552},  # input movie itself, skipped
                            {"id": 12551},  # Creepshow 2
                            {"id": 50122},  # Creepshow 3
                        ],
                    },
                ),
                _build_response(  # /recommendations
                    json_data={"results": [{"id": 999}]},
                ),
            ],
        )

        ids = await client.get_movie_recommendations(12552)

        assert ids == [12551, 50122, 999]

    @pytest.mark.asyncio
    async def test_dedupes_overlap_between_collection_and_recommendations(self) -> None:
        # Same id appearing in both sources renders once at the
        # collection's position (highest relevance).
        client = _make_client(
            get_responses=[
                _build_response(  # /movie/{id}
                    json_data={"belongs_to_collection": {"id": 1}},
                ),
                _build_response(  # /collection/1
                    json_data={"parts": [{"id": 100}, {"id": 200}]},
                ),
                _build_response(  # /recommendations
                    json_data={"results": [{"id": 200}, {"id": 300}]},
                ),
            ],
        )

        ids = await client.get_movie_recommendations(50)

        assert ids == [100, 200, 300]

    @pytest.mark.asyncio
    async def test_collection_lookup_failure_falls_through_to_recommendations(self) -> None:
        # The collection endpoint flaking shouldn't sink the rest
        # of the lookup — recommendations still come back.
        client = _make_client(
            get_responses=[
                _build_response(  # /movie/{id}
                    json_data={"belongs_to_collection": {"id": 1}},
                ),
                _build_response(status_code=500),  # /collection/1 fails
                _build_response(  # /recommendations still works
                    json_data={"results": [{"id": 999}]},
                ),
            ],
        )

        ids = await client.get_movie_recommendations(50)

        assert ids == [999]


@pytest.mark.unit
class TestGetSeriesRecommendations:
    """``get_series_recommendations`` — ML / heuristic merge.

    Series have no collection equivalent on TMDB, so the call sequence
    is just:

    1. ``/tv/{id}/recommendations`` for ML-based recs.
    2. ``/tv/{id}/similar`` only when recommendations is empty.
    """

    @pytest.mark.asyncio
    async def test_returns_recommended_ids_in_order(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(  # /tv/{id}/recommendations
                    json_data={"results": [{"id": 60059}, {"id": 1396}, {"id": 60625}]},
                ),
            ],
        )

        ids = await client.get_series_recommendations(1396)

        # 1396 is the input series itself — must be skipped.
        assert ids == [60059, 60625]

    @pytest.mark.asyncio
    async def test_falls_back_to_similar_when_recommendations_empty(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data={"results": []}),  # /recommendations
                _build_response(  # /similar
                    json_data={"results": [{"id": 99}, {"id": 100}]},
                ),
            ],
        )

        ids = await client.get_series_recommendations(42)

        assert ids == [99, 100]

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_sources_empty(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(json_data={"results": []}),  # /recommendations
                _build_response(json_data={"results": []}),  # /similar
            ],
        )

        ids = await client.get_series_recommendations(42)

        assert ids == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self) -> None:
        client = _make_client(
            get_responses=[
                _build_response(status_code=500),  # /recommendations
                _build_response(status_code=500),  # /similar
            ],
        )

        ids = await client.get_series_recommendations(42)

        assert ids == []

    @pytest.mark.asyncio
    async def test_skips_non_int_ids_in_payload(self) -> None:
        # Defensive: a malformed TMDB row shouldn't crash the parser.
        client = _make_client(
            get_responses=[
                _build_response(  # /recommendations
                    json_data={
                        "results": [
                            {"id": 1},
                            {"id": "not-an-int"},
                            {"name": "no id here"},
                            {"id": 2},
                        ]
                    },
                ),
            ],
        )

        ids = await client.get_series_recommendations(1396)

        assert ids == [1, 2]


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

    @pytest.mark.asyncio
    async def test_should_parse_cast_from_credits_append(self) -> None:
        """The series details fetch appends ``credits`` so TMDB returns
        a top-billed cast list. Pin that the client surfaces it on
        ``MediaMetadata.cast`` the same way the movie path does."""
        data = _series_details()
        data["credits"] = {
            "cast": [
                {
                    "id": 17419,
                    "name": "Bryan Cranston",
                    "character": "Walter White",
                    "profile_path": "/bryan.jpg",
                    "order": 0,
                },
                {
                    "id": 84497,
                    "name": "Aaron Paul",
                    "character": "Jesse Pinkman",
                    "profile_path": "/aaron.jpg",
                    "order": 1,
                },
            ],
            "crew": [],
        }
        client = _make_client(
            get_responses=[
                _build_response(json_data=data),
                _build_response(json_data=_season_details()),
            ]
        )

        result = await client._fetch_series_details(1396)

        assert result is not None
        assert len(result.cast) == 2
        assert result.cast[0].name == "Bryan Cranston"
        assert result.cast[0].role == "Walter White"
        assert result.cast[0].tmdb_id == 17419
        assert result.cast[0].profile_url is not None
        assert result.cast[1].name == "Aaron Paul"


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
