"""Tests for CreditsSkipMode enum."""

import pytest

from src.modules.preferences.domain.value_objects import CreditsSkipMode


@pytest.mark.unit
class TestCreditsSkipMode:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("manual", CreditsSkipMode.MANUAL),
            ("auto", CreditsSkipMode.AUTO),
        ],
    )
    def test_should_build_from_canonical_strings(self, raw: str, expected: CreditsSkipMode) -> None:
        assert CreditsSkipMode(raw) is expected

    def test_should_reject_unknown_value(self) -> None:
        with pytest.raises(ValueError, match="'off'"):
            CreditsSkipMode("off")

    def test_should_not_share_intro_only_modes(self) -> None:
        # ``autoAfterFirst`` is meaningful for an opening sequence and
        # meaningless for credits — the two enums stay separate rather
        # than exposing a value one side can't honour.
        with pytest.raises(ValueError, match="'autoAfterFirst'"):
            CreditsSkipMode("autoAfterFirst")
