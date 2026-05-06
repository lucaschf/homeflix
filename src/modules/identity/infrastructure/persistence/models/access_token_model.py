"""AccessToken SQLAlchemy ORM model — server-side session storage.

Implements the session storage decided in ADR-011 (server-side session
via ``DatabaseStrategy`` + ``CookieTransport``). The opaque token is
the primary key; revocation is hard ``DELETE``. There is no
``external_id`` (the secret must never be exposed) and no soft-delete
(logout = removal).

The user_id FK declared on ``SQLAlchemyBaseAccessTokenTableUUID``
points to ``"user.id"`` by default — we override it to target our
own ``users`` table.
"""

import uuid

from fastapi_users_db_sqlalchemy.access_token import (
    SQLAlchemyBaseAccessTokenTableUUID,
)
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import BaseSecret


class AccessTokenModel(SQLAlchemyBaseAccessTokenTableUUID, BaseSecret):
    """SQLAlchemy model for the ``access_tokens`` table.

    Inherited from ``SQLAlchemyBaseAccessTokenTableUUID``:
        - ``token`` (String(43), primary key — opaque secret)
        - ``created_at`` (TIMESTAMPAware, server-default ``now_utc``)

    Overridden:
        - ``user_id``: FK retargeted from default ``"user.id"`` to
          ``"users.id"`` (our table is named ``users``, not ``user``).

    Added:
        - ``current_profile_id``: nullable FK to ``profiles.id``,
          ``ON DELETE SET NULL``. Updated by the profile-switch use
          case; lets each session carry its own active profile so
          multi-device usage with different profiles works correctly.
    """

    __tablename__ = "access_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    current_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
    )


__all__ = ["AccessTokenModel"]
