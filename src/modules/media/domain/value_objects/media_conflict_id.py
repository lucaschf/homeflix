"""MediaConflictId external id."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class MediaConflictId(ExternalId):
    """External ID for media conflict records.

    Format: ``cnf_{base62_12chars}``. Identifies a single detected
    candidate-pair collision in the operator-facing conflict queue
    (ADR-015). Not part of the playable ``MediaId`` union — conflicts
    are operational metadata, not addressable content.
    """

    EXPECTED_PREFIX: ClassVar[str] = "cnf"


__all__ = ["MediaConflictId"]
