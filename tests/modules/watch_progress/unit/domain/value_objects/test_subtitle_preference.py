"""Tests for the SubtitlePreference value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.watch_progress.domain.value_objects import SubtitlePreference


@pytest.mark.unit
class TestSubtitlePreferenceConstruction:
    """Factory methods and the off/track distinction."""

    def test_track_holds_index_and_is_not_off(self) -> None:
        pref = SubtitlePreference.track(3)
        assert pref.track_index == 3
        assert pref.is_off is False

    def test_off_has_no_index_and_is_off(self) -> None:
        pref = SubtitlePreference.off()
        assert pref.track_index is None
        assert pref.is_off is True

    def test_off_and_track_are_not_equal(self) -> None:
        assert SubtitlePreference.off() != SubtitlePreference.track(0)

    def test_negative_track_index_is_rejected(self) -> None:
        with pytest.raises(DomainValidationException):
            SubtitlePreference.track(-1)


@pytest.mark.unit
class TestSubtitlePreferenceWireCodec:
    """from_wire / to_wire isolate the -1 sentinel and None semantics."""

    def test_none_is_no_preference(self) -> None:
        assert SubtitlePreference.from_wire(None) is None
        assert SubtitlePreference.to_wire(None) is None

    def test_negative_decodes_to_off_and_encodes_back(self) -> None:
        assert SubtitlePreference.from_wire(-1) == SubtitlePreference.off()
        assert SubtitlePreference.to_wire(SubtitlePreference.off()) == -1

    def test_index_round_trips(self) -> None:
        assert SubtitlePreference.from_wire(0) == SubtitlePreference.track(0)
        assert SubtitlePreference.to_wire(SubtitlePreference.track(5)) == 5

    @pytest.mark.parametrize("wire", [None, -1, 0, 1, 7])
    def test_wire_round_trip(self, wire: int | None) -> None:
        assert SubtitlePreference.to_wire(SubtitlePreference.from_wire(wire)) == wire

    def test_non_canonical_negative_decodes_to_off_and_canonicalizes(self) -> None:
        # Decoding is lenient (any negative is "off"); encoding canonicalises to -1.
        assert SubtitlePreference.from_wire(-5) == SubtitlePreference.off()
        assert SubtitlePreference.to_wire(SubtitlePreference.from_wire(-5)) == -1
