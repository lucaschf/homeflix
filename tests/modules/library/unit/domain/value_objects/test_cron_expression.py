"""Tests for the CronExpression value object."""

import pytest
from apscheduler.triggers.cron import CronTrigger

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.library.domain.value_objects.cron_expression import CronExpression

# Expressions the VO must accept. Reused by the divergence test below to
# assert every VO-valid expression is also accepted by the real scheduler
# parser (APScheduler ``from_crontab``), so a saved cron always fires.
_VALID_EXPRESSIONS = [
    "30 5 * * *",
    "0 0 * * 0",
    "*/15 * * * *",
    "0 */6 1-15 * 1-5",
    "0,30 9-17 * * mon-fri",
    "0 0 1 jan,jul *",
    "15 2 * 1-12/2 SUN",
    "0 0 * * fri-sun",  # ascending DOW range (mon=0..sun=6)
]


@pytest.mark.unit
class TestCronExpressionValid:
    """Expressions that should parse and round-trip their value."""

    @pytest.mark.parametrize("expr", _VALID_EXPRESSIONS)
    def test_accepts_valid_expression(self, expr: str) -> None:
        assert CronExpression(expr).value == expr


@pytest.mark.unit
@pytest.mark.parametrize("expr", _VALID_EXPRESSIONS)
def test_valid_expression_is_accepted_by_scheduler_parser(expr: str) -> None:
    # The VO's grammar must stay a subset of the scheduler's, otherwise a
    # cron passes domain validation, is persisted, and then silently never
    # fires when the scheduler rejects it.
    CronTrigger.from_crontab(expr, timezone="UTC")


@pytest.mark.unit
class TestCronExpressionInvalid:
    """Expressions that must be rejected at construction."""

    @pytest.mark.parametrize(
        "expr",
        [
            "99 99 99 99 99",  # every field out of range
            "60 * * * *",  # minute upper bound is 59
            "* 24 * * *",  # hour upper bound is 23
            "* * 0 * *",  # day of month lower bound is 1
            "* * * 13 *",  # month upper bound is 12
            "* * * * 7",  # day of week upper bound is 6 (APScheduler convention)
            "* * * *",  # only four fields
            "* * * * * *",  # six fields
            "",  # empty
            "*/0 * * * *",  # step must be >= 1
            "5-1 * * * *",  # inverted range
            "* * * jan-3 *",  # mixed name/number range
            "1,,2 * * * *",  # empty list item
            "abc * * * *",  # non-numeric, no name alias for minute
        ],
    )
    def test_rejects_invalid_expression(self, expr: str) -> None:
        with pytest.raises(DomainValidationException):
            CronExpression(expr)


@pytest.mark.unit
def test_equality_is_type_scoped() -> None:
    assert CronExpression("0 0 * * *") == CronExpression("0 0 * * *")
    assert CronExpression("0 0 * * *") != CronExpression("0 1 * * *")
