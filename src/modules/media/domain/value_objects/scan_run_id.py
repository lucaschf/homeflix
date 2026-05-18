"""ScanRunId external id."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class ScanRunId(ExternalId):
    """External ID for scan/enrich runs.

    A single ``scan_runs`` table backs both kinds of admin runs
    (catalog scan + bulk metadata enrich), so the prefix is the
    generic ``run`` rather than something kind-specific. Format:
    ``run_{base62_12chars}``.
    """

    EXPECTED_PREFIX: ClassVar[str] = "run"


__all__ = ["ScanRunId"]
