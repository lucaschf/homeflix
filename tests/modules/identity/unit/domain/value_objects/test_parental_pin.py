"""Tests for the ParentalPin value object (ADR-035, Amendment 7 D4)."""

import json
import traceback

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.identity.domain.rule_codes import IdentityRuleCodes
from src.modules.identity.domain.value_objects.parental_pin import ParentalPin

pytestmark = pytest.mark.unit


class TestParentalPinAcceptance:
    @pytest.mark.parametrize("raw", ["000000", "123456", "987654"])
    def test_should_accept_exactly_six_ascii_digits(self, raw: str) -> None:
        assert ParentalPin(raw).value == raw


class TestParentalPinRejection:
    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("12345", id="five-digits"),
            pytest.param("1234567", id="seven-digits"),
            pytest.param("1234", id="four-digits"),
            pytest.param("12a456", id="letter"),
            pytest.param("\u0661\u0662\u0663\u0664\u0665\u0666", id="arabic-indic-digits"),
            pytest.param("\uff11\uff12\uff13\uff14\uff15\uff16", id="fullwidth-digits"),
            pytest.param("123456\n", id="trailing-newline"),
            pytest.param(" 123456", id="leading-space"),
            pytest.param("", id="empty"),
        ],
    )
    def test_should_reject_anything_but_six_ascii_digits(self, raw: str) -> None:
        with pytest.raises(DomainValidationException) as exc_info:
            ParentalPin(raw)

        assert exc_info.value.message_code == IdentityRuleCodes.PARENTAL_PIN_INVALID_FORMAT

    @pytest.mark.parametrize("raw", [None, 123456])
    def test_should_reject_non_strings(self, raw: object) -> None:
        with pytest.raises(DomainValidationException):
            ParentalPin(raw)

    def test_rejection_should_carry_no_trace_of_the_value(self) -> None:
        # The generic Pydantic conversion puts the raw input in
        # ``details[].metadata.input``, which the handler echoes in the 422.
        raw = "98a765"

        with pytest.raises(DomainValidationException) as exc_info:
            ParentalPin(raw)

        exc = exc_info.value
        assert raw not in json.dumps(exc.to_dict(include_internal=True), default=str)
        assert raw not in "".join(traceback.format_exception(exc))
        assert exc.__cause__ is None
        assert exc.__suppress_context__ is True


class TestParentalPinMasking:
    def test_repr_should_not_contain_the_digits(self) -> None:
        pin = ParentalPin("904518")

        assert "904518" not in repr(pin)
        assert repr(pin) == "ParentalPin(******)"

    def test_str_and_format_should_not_contain_the_digits(self) -> None:
        pin = ParentalPin("904518")

        assert "904518" not in str(pin)
        assert "904518" not in f"{pin}"
        assert "904518" not in repr([pin])
