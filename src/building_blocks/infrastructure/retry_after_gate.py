"""Gate that remembers until when a provider asked us to stop calling it.

A ``429 Too Many Requests`` with ``Retry-After`` is a statement about the
provider, not about the request that received it: every caller sharing the
same credentials is throttled. One gate per provider client lets the first
``429`` stop the others before they send, instead of each one discovering the
limit on its own (ADR-038).

The gate only keeps time. Whether to wait for it or give up is decided by
the caller's budget (:func:`src.building_blocks.application.deadline`).
"""

import time
from collections.abc import Callable


class RetryAfterGate:
    """Track the moment a provider reopens after asking us to back off.

    Args:
        clock: Monotonic clock in seconds. Injected for tests.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._reopens_at = 0.0

    def close_for(self, seconds: float) -> None:
        """Keep the gate closed for at least ``seconds`` from now.

        A shorter closure never reopens a gate an earlier, longer one closed.
        """
        self._reopens_at = max(self._reopens_at, self._clock() + seconds)

    def seconds_until_open(self) -> float:
        """Return how long until the provider accepts calls again (``0`` if open)."""
        return max(0.0, self._reopens_at - self._clock())


__all__ = ["RetryAfterGate"]
