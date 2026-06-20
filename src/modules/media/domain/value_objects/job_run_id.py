"""JobRunId external id."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class JobRunId(ExternalId):
    """External ID for a recorded scheduler job execution.

    One ``job_runs`` row per tick of any background job (backfill,
    detection, scans, etc.). Format: ``job_{base62_12chars}``.
    """

    EXPECTED_PREFIX: ClassVar[str] = "job"


__all__ = ["JobRunId"]
