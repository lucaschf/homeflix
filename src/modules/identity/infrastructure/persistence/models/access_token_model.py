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
from sqlalchemy import ForeignKey, Integer, text
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
        - Parental unlock and lockout state, per session and so per
          device (ADR-035, Amendment 7 D4): ``parental_failed_attempts``,
          ``parental_lockouts`` (the ladder step), ``parental_locked_until``
          (end of the last lock, kept after it passes) and
          ``parental_unlock_until``. Times are integer epoch seconds (UTC)
          so the lockout can compare them atomically in SQL. The NOT NULL
          counters carry a server default because FastAPI Users' login
          inserts only ``token`` and ``user_id``.
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
    parental_failed_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    parental_lockouts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    parental_locked_until: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parental_unlock_until: Mapped[int | None] = mapped_column(Integer, nullable=True)


__all__ = ["AccessTokenModel"]
