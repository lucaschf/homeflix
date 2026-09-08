"""Unit tests for the artwork variant value objects (ADR-034)."""

from __future__ import annotations

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.metadata.domain.value_objects.artwork_variant import (
    ALLOWED_ARTWORK_WIDTHS,
    ARTWORK_WIDTH_LADDER,
    ArtworkKind,
    ArtworkWidth,
)


class TestArtworkWidth:
    @pytest.mark.parametrize("width", sorted(ALLOWED_ARTWORK_WIDTHS))
    def test_should_accept_every_ladder_width(self, width: int) -> None:
        assert ArtworkWidth(width).value == width

    @pytest.mark.parametrize("width", [0, -1, 1, 999, 1281, 4000])
    def test_should_reject_off_ladder_widths(self, width: int) -> None:
        with pytest.raises(DomainValidationException):
            ArtworkWidth(width)

    def test_should_reject_non_integers(self) -> None:
        with pytest.raises(DomainValidationException):
            ArtworkWidth("780")  # type: ignore[arg-type]


class TestLadder:
    def test_should_cover_every_kind(self) -> None:
        assert set(ARTWORK_WIDTH_LADDER) == set(ArtworkKind)

    def test_should_be_ascending_per_kind_and_exactly_the_allowed_union(self) -> None:
        seen: set[int] = set()
        for widths in ARTWORK_WIDTH_LADDER.values():
            values = [width.value for width in widths]
            assert values == sorted(values)
            seen.update(values)
        # The route accepts exactly what some kind can be asked for —
        # no dead widths, none missing.
        assert seen == ALLOWED_ARTWORK_WIDTHS
