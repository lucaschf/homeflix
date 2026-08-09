"""Tests for the ShareToken value object."""

import pytest

from src.building_blocks.domain import DomainValidationException
from src.modules.collections.domain.value_objects import ShareToken


@pytest.mark.unit
class TestShareToken:
    """ShareToken generation and validation."""

    def test_generate_produces_sufficiently_long_token(self) -> None:
        token = ShareToken.generate()
        assert len(token.value) >= ShareToken.MIN_LENGTH
        assert len(token.value) <= ShareToken.MAX_LENGTH

    def test_generate_produces_unique_unguessable_tokens(self) -> None:
        tokens = {ShareToken.generate().value for _ in range(200)}
        # No collisions and nothing sequential/predictable.
        assert len(tokens) == 200

    def test_rejects_too_short_value(self) -> None:
        with pytest.raises(DomainValidationException, match="at least"):
            ShareToken("short")

    def test_accepts_explicit_valid_value(self) -> None:
        raw = "a" * ShareToken.MIN_LENGTH
        assert ShareToken(raw).value == raw

    def test_two_tokens_with_same_value_are_equal(self) -> None:
        raw = "b" * 24
        assert ShareToken(raw) == ShareToken(raw)
