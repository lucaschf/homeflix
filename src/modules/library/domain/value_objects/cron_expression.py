"""Cron expression value object."""

from typing import ClassVar

from pydantic import ConfigDict, model_validator

from src.building_blocks.domain.value_objects import StringValueObject

# Three-letter aliases accepted (case-insensitive) in the month and
# day-of-week fields, mapped to their numeric value. The day-of-week
# numbering follows the scheduler's parser (APScheduler ``from_crontab``):
# 0 = Monday .. 6 = Sunday — not standard cron's 0 = Sunday. Keeping the
# numbering aligned with the real consumer is what stops a syntactically
# valid expression from being accepted here yet silently never firing.
_MONTH_NAMES = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}
_DOW_NAMES = {
    name: number
    for number, name in enumerate(
        ("mon", "tue", "wed", "thu", "fri", "sat", "sun"),
        start=0,
    )
}

# (field name, inclusive low, inclusive high, optional name→number aliases).
_FIELDS: tuple[tuple[str, int, int, dict[str, int] | None], ...] = (
    ("minute", 0, 59, None),
    ("hour", 0, 23, None),
    ("day of month", 1, 31, None),
    ("month", 1, 12, _MONTH_NAMES),
    ("day of week", 0, 6, _DOW_NAMES),  # 0 = Monday .. 6 = Sunday (APScheduler)
)


def _resolve_value(
    token: str, field: str, low: int, high: int, names: dict[str, int] | None
) -> int:
    """Resolve a single numeric/named token and check its range."""
    key = token.strip().lower()
    if names and key in names:
        return names[key]
    if not key.isdigit():
        raise ValueError(f"Invalid value '{token}' in {field} field")
    value = int(key)
    if not low <= value <= high:
        raise ValueError(f"Value '{value}' out of range [{low}, {high}] in {field} field")
    return value


def _validate_part(
    part: str, field: str, low: int, high: int, names: dict[str, int] | None
) -> None:
    """Validate one comma-separated item of a cron field."""
    base, sep, step = part.partition("/")
    if sep and (not step.isdigit() or int(step) < 1):
        raise ValueError(f"Invalid step '{step}' in {field} field: '{part}'")

    if base == "*":
        return

    start, dash, end = base.partition("-")
    if dash:
        # The scheduler's parser rejects mixed name/number range ends
        # (e.g. ``jan-3``), so require both ends to be the same kind.
        start_is_name = names is not None and start.strip().lower() in names
        end_is_name = names is not None and end.strip().lower() in names
        if start_is_name != end_is_name:
            raise ValueError(f"Mixed name/number range '{base}' in {field} field")
        low_bound = _resolve_value(start, field, low, high, names)
        high_bound = _resolve_value(end, field, low, high, names)
        if low_bound > high_bound:
            raise ValueError(f"Inverted range '{base}' in {field} field")
        return

    _resolve_value(base, field, low, high, names)


class CronExpression(StringValueObject):
    """A validated 5-field cron expression (``minute hour dom month dow``).

    Each field is checked against its real range rather than a loose
    "five space-separated tokens" regex, so a semantically-invalid
    expression (e.g. ``99 99 99 99 99``) is rejected at the domain
    boundary instead of being persisted and silently never firing.

    Supported per field: ``*``, ``*/step``, ``a``, ``a-b``, ``a-b/step``
    and comma-separated lists of those. Month and day-of-week fields also
    accept case-insensitive three-letter names (``jan``..``dec``,
    ``mon``..``sun``). Ranges must be ascending (``mon-fri``, not the
    wrap-around ``fri-mon``); express a wrap as a list (``fri,sat,sun``).
    Day-of-week numbering follows the scheduler's parser (0 = Monday ..
    6 = Sunday); prefer names to avoid the off-by-one against standard
    cron. The grammar accepted here is a strict subset of what the
    scheduler accepts, so a valid expression always schedules.

    Example:
        >>> CronExpression("30 5 * * *").value
        '30 5 * * *'
        >>> CronExpression("0 */6 1-15 jan-mar mon-fri").value
        '0 */6 1-15 jan-mar mon-fri'
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, str_strip_whitespace=True)

    @model_validator(mode="after")
    def _validate_cron(self) -> "CronExpression":
        fields = self.root.split()
        if len(fields) != 5:
            raise ValueError(
                f"Cron expression must have 5 fields, got {len(fields)}: '{self.root}'"
            )
        for token, (name, low, high, names) in zip(fields, _FIELDS, strict=True):
            for part in token.split(","):
                _validate_part(part, name, low, high, names)
        return self


__all__ = ["CronExpression"]
