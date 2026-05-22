"""Scheduler tunables — master switch and reconcile interval."""

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class SchedulerConfig(CompoundValueObject):
    """Operational knobs for the background job scheduler.

    Attributes:
        enabled: Master switch for the scheduler that drives every
            periodic job (library scans, thumbnail backfill, intro
            detection). When ``False`` no job ticks, even if its
            per-job switch is on.
        reconcile_interval_minutes: How often the scheduler re-reads
            library schedules from the database to sync cron jobs with
            their configured cadence. Lower values pick up schedule
            edits sooner; higher values reduce idle DB chatter.

    Example:
        >>> cfg = SchedulerConfig(enabled=True, reconcile_interval_minutes=5)
        >>> faster = cfg.with_updates(reconcile_interval_minutes=2)
    """

    enabled: bool = Field(default=True)
    reconcile_interval_minutes: int = Field(default=5, ge=1)


__all__ = ["SchedulerConfig"]
