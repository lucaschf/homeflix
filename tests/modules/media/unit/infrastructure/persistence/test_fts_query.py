"""Tests for the FTS5 query preparation and hit-ordering helpers."""

from types import SimpleNamespace

import pytest

from src.modules.media.infrastructure.persistence.repositories.movie_repository import (
    _by_rank_then_title,
    _prepare_fts_query,
)


@pytest.mark.unit
class TestPrepareFtsQuery:
    """Sanitization and prefix-matching behavior."""

    def test_should_append_wildcard_to_last_token(self) -> None:
        assert _prepare_fts_query("inception") == "inception*"

    def test_should_append_wildcard_only_to_last_token_for_multi_word(self) -> None:
        assert _prepare_fts_query("jackie chan") == "jackie chan*"

    def test_should_strip_fts_operators(self) -> None:
        assert _prepare_fts_query('"hello" -world +foo') == "hello world foo*"

    def test_should_return_empty_for_blank_input(self) -> None:
        assert _prepare_fts_query("") == ""
        assert _prepare_fts_query("   ") == ""

    def test_should_return_empty_for_only_operators(self) -> None:
        assert _prepare_fts_query('"" - + \'') == ""

    def test_should_handle_single_character_query(self) -> None:
        assert _prepare_fts_query("a") == "a*"

    def test_should_preserve_accented_characters(self) -> None:
        assert _prepare_fts_query("ação") == "ação*"

    def test_should_strip_leading_trailing_whitespace(self) -> None:
        assert _prepare_fts_query("  test  ") == "test*"


def _hit(title: str, rank: float) -> tuple[SimpleNamespace, float]:
    return SimpleNamespace(title=SimpleNamespace(value=title)), rank


@pytest.mark.unit
class TestByRankThenTitle:
    """Ordering of FTS hits once ranks are pooled in Python."""

    def test_should_put_more_negative_rank_first(self) -> None:
        hits = [_hit("Zulu", -1.0), _hit("Alien", -5.0), _hit("Mars", -3.0)]

        ordered = sorted(hits, key=_by_rank_then_title)

        assert [h[0].title.value for h in ordered] == ["Alien", "Mars", "Zulu"]

    def test_should_break_ties_by_title(self) -> None:
        # bm25() returned NULL for every row of a one-letter prefix query,
        # so all ranks were coalesced to 0.0 — the page must still come
        # back in a stable order instead of rowid order.
        hits = [_hit("Blade", 0.0), _hit("Alien", 0.0), _hit("Batman", 0.0)]

        ordered = sorted(hits, key=_by_rank_then_title)

        assert [h[0].title.value for h in ordered] == ["Alien", "Batman", "Blade"]

    def test_should_place_unranked_hits_after_ranked_ones(self) -> None:
        hits = [_hit("Unranked", 0.0), _hit("Ranked", -0.5)]

        ordered = sorted(hits, key=_by_rank_then_title)

        assert [h[0].title.value for h in ordered] == ["Ranked", "Unranked"]
