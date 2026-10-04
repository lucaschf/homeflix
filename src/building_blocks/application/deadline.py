"""Ambient deadline: how long the current caller tolerates waiting on I/O.

A caller that runs work crossing I/O boundaries declares its budget once::

    async with deadline(60):
        await enrich(...)

The budget does **not** cancel anything. Adapters that wait on a remote
service read :func:`remaining_seconds` and bound every wait, retry and call
by what is left, so the remote side can never hold the caller past its
budget, while local work in the same block (a database write, an event
publish) is never interrupted half-way (ADR-038). Outside any scope there is
no budget and :func:`remaining_seconds` returns ``None``: code that would
wait or retry must treat that as "fail fast".

The budget travels in a ``ContextVar`` instead of a parameter on every port
method (ADR-038). Nested scopes can only shorten the budget, never extend it.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

_DEADLINE: ContextVar[float | None] = ContextVar("deadline", default=None)


@asynccontextmanager
async def deadline(seconds: float) -> AsyncIterator[None]:
    """Declare a budget of ``seconds`` for remote waits in the enclosed block.

    Args:
        seconds: Maximum time the block may spend waiting on remote
            services. Clamped by any enclosing deadline, so an inner scope
            never outlives its caller's.

    Yields:
        Nothing; the budget is read through :func:`remaining_seconds`.
    """
    when = asyncio.get_running_loop().time() + seconds
    outer = _DEADLINE.get()
    if outer is not None:
        when = min(when, outer)
    token = _DEADLINE.set(when)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def remaining_seconds() -> float | None:
    """Return the time left in the current budget, or ``None`` without one."""
    when = _DEADLINE.get()
    if when is None:
        return None
    return max(0.0, when - asyncio.get_running_loop().time())


__all__ = ["deadline", "remaining_seconds"]
