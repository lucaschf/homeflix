"""User external ID value object."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class UserId(ExternalId):
    """External ID for users.

    Format: usr_{base62_12chars}
    Example: usr_2xK9mPqR7nL4

    The internal database PK is a UUID (FastAPI Users requirement); this
    prefixed external ID is what every other layer (domain, application,
    presentation) sees. Translation happens in the SQLAlchemy mapper.
    See ADR-010.

    Example:
        >>> user_id = UserId.generate()
        >>> user_id.prefix
        'usr'
        >>> UserId("usr_2xK9mPqR7nL4")
        UserId('usr_2xK9mPqR7nL4')
    """

    EXPECTED_PREFIX: ClassVar[str] = "usr"


__all__ = ["UserId"]
