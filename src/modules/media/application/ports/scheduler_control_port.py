"""Port for issuing control commands to the background scheduler."""

from abc import ABC, abstractmethod


class SchedulerControlPort(ABC):
    """Write-side window into the live scheduler for admin actions.

    Kept separate from :class:`SchedulerInspectorPort` so the read path
    (the Jobs dashboard) stays side-effect free while admin "run now"
    actions go through an explicitly mutating contract.
    """

    @abstractmethod
    def trigger(self, job_id: str) -> bool:
        """Schedule ``job_id`` to fire as soon as possible.

        Args:
            job_id: Stable scheduler job id to run immediately.

        Returns:
            ``True`` when the job was registered and rescheduled to run
            now; ``False`` when no such job is currently registered.
        """
        ...


__all__ = ["SchedulerControlPort"]
