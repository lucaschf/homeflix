"""Port for launching an out-of-band intro-detection run."""

from abc import ABC, abstractmethod

from src.modules.media.domain.value_objects import SeasonId


class IntroDetectionRunnerPort(ABC):
    """Write-side hook for running intro detection on demand.

    The periodic job owns the eligibility queue; this port covers the
    operator action "detect this season now". Detection decodes and
    fingerprints every episode of the season and routinely takes
    minutes, so implementations run it off the request path rather than
    awaiting it inline.
    """

    @abstractmethod
    def start_for_season(self, season_id: SeasonId) -> bool:
        """Start detection for one season in the background.

        Args:
            season_id: External id of the season to process (ssn_xxx).

        Returns:
            ``True`` when a run was started; ``False`` when one is
            already in flight for that season — the caller should treat
            the running one as the answer instead of queueing a second.
        """
        ...


__all__ = ["IntroDetectionRunnerPort"]
