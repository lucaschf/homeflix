"""Profile external ID value object."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class ProfileId(ExternalId):
    """External ID for profiles.

    Format: prf_{base62_12chars}
    Example: prf_2xK9mPqR7nL4

    Profile is the personalization context referenced cross-BC. Outside
    the identity BC, every consumer (watch_progress, collections,
    preferences) references ProfileId — never UserId. See ADR-010.

    Example:
        >>> profile_id = ProfileId.generate()
        >>> profile_id.prefix
        'prf'
        >>> ProfileId("prf_2xK9mPqR7nL4")
        ProfileId('prf_2xK9mPqR7nL4')
    """

    EXPECTED_PREFIX: ClassVar[str] = "prf"


__all__ = ["ProfileId"]
