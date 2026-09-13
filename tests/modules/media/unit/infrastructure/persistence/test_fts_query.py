"""Tests for the FTS5 query preparation helper."""

import pytest

from src.modules.media.infrastructure.persistence.repositories.movie_repository import (
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
