"""Tests for Speed value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.preferences.domain.value_objects import Speed


@pytest.mark.unit
class TestSpeed:
    def test_should_accept_default_rate(self) -> None:
        assert Speed(1.0).value == 1.0

    def test_should_accept_min_bound(self) -> None:
        assert Speed(0.25).value == 0.25

    def test_should_accept_max_bound(self) -> None:
        assert Speed(4.0).value == 4.0

    def test_should_reject_below_min(self) -> None:
        with pytest.raises(DomainValidationException):
            Speed(0.1)

    def test_should_reject_above_max(self) -> None:
        with pytest.raises(DomainValidationException):
            Speed(5.0)

    def test_should_coerce_integers(self) -> None:
        assert Speed(2).value == 2.0

    def test_should_reject_non_numeric(self) -> None:
        with pytest.raises(DomainValidationException):
            Speed("fast")  # type: ignore[arg-type]
