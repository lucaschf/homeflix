"""DTOs for direct byte-range streaming.

Encapsulates everything the route needs to build a ``StreamingResponse``
so presentation code stays free of streaming concepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass(frozen=True)
class RangeStreamOutput:
    """Byte-range streaming response pieces.

    ``body`` is the async generator of chunks to stream; the route
    wraps it in a FastAPI ``StreamingResponse`` with the provided
    status code and headers so response construction stays in
    presentation.
    """

    status_code: int
    media_type: str
    headers: dict[str, str]
    body: AsyncIterator[bytes]


__all__ = ["RangeStreamOutput"]
