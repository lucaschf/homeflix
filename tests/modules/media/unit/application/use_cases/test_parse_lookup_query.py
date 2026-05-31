"""Tests for the catalog-request lookup query parser."""

import pytest

from src.modules.media.application.use_cases.search_tmdb_titles import (
    parse_lookup_query,
)


class TestParseLookupQuery:
    @pytest.mark.parametrize("raw", ["", "   ", "\n\t"])
    def test_empty_or_whitespace_returns_none(self, raw: str) -> None:
        assert parse_lookup_query(raw) is None

    def test_tmdb_movie_url(self) -> None:
        parsed = parse_lookup_query("https://www.themoviedb.org/movie/603-the-matrix")
        assert parsed is not None
        assert parsed.kind == "tmdb_id"
        assert parsed.tmdb_id == 603
        assert parsed.media_type == "movie"

    def test_tmdb_tv_url(self) -> None:
        parsed = parse_lookup_query("https://www.themoviedb.org/tv/1399")
        assert parsed is not None
        assert parsed.kind == "tmdb_id"
        assert parsed.tmdb_id == 1399
        assert parsed.media_type == "tv"

    def test_imdb_url(self) -> None:
        parsed = parse_lookup_query("https://www.imdb.com/title/tt0133093/")
        assert parsed is not None
        assert parsed.kind == "imdb_id"
        assert parsed.imdb_id == "tt0133093"

    def test_imdb_url_case_insensitive(self) -> None:
        parsed = parse_lookup_query("HTTPS://IMDB.COM/title/TT0133093/")
        assert parsed is not None
        assert parsed.kind == "imdb_id"
        # Canonical lowercase, regardless of input casing.
        assert parsed.imdb_id == "tt0133093"

    def test_bare_imdb_id(self) -> None:
        parsed = parse_lookup_query("tt0133093")
        assert parsed is not None
        assert parsed.kind == "imdb_id"
        assert parsed.imdb_id == "tt0133093"

    def test_bare_tmdb_numeric_is_ambiguous(self) -> None:
        parsed = parse_lookup_query("603")
        assert parsed is not None
        assert parsed.kind == "tmdb_id"
        assert parsed.tmdb_id == 603
        # Ambiguous — caller fetches both /movie and /tv.
        assert parsed.media_type is None

    def test_plain_text_falls_back_to_text_branch(self) -> None:
        parsed = parse_lookup_query("  The Matrix  ")
        assert parsed is not None
        assert parsed.kind == "text"
        assert parsed.text == "The Matrix"

    def test_text_branch_for_unknown_url(self) -> None:
        # A URL that's neither TMDB nor IMDb falls through to the
        # text branch — the search hopefully still finds something.
        parsed = parse_lookup_query("https://example.com/movie/foo")
        assert parsed is not None
        assert parsed.kind == "text"
        assert parsed.text == "https://example.com/movie/foo"

    def test_too_short_imdb_id_is_text(self) -> None:
        # "tt1" is not a real IMDb id (min 6 digits). Fall through.
        parsed = parse_lookup_query("tt1")
        assert parsed is not None
        assert parsed.kind == "text"
