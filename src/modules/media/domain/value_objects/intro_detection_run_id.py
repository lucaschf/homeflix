"""IntroDetectionRunId external id."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class IntroDetectionRunId(ExternalId):
    """External ID for intro-detection audit runs.

    One row is appended per season the detection job processes.
    Format: ``idr_{base62_12chars}``.
    """

    EXPECTED_PREFIX: ClassVar[str] = "idr"


__all__ = ["IntroDetectionRunId"]
