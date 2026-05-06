"""Profile SQLAlchemy ORM model."""

import uuid

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import BaseWithUUID


class ProfileModel(BaseWithUUID):
    """SQLAlchemy model for the ``Profile`` aggregate.

    Profiles are personalization contexts owned by a ``User`` (FK
    ``user_id``). The PK is a UUID for consistency with the identity
    BC's UUID-PK convention; clients reference profiles by their
    prefixed ``external_id`` (``prf_xxxxxxxxxxxx``) — translation
    happens in ``ProfileMapper``.

    Attributes:
        user_id: UUID of the owning ``UserModel``. ``ON DELETE CASCADE``
            so deleting an account also removes its profiles.
        name: Display name shown in the profile picker (1..50 chars).
        avatar_url: Optional URL to an avatar image.
        is_kids: Marks the profile as kids-mode (UX hint independent
            of the ACL).
        allowed_library_ids: JSON-encoded list of library external_ids
            (``lib_xxx``) this profile may see in the catalog. Stored
            as TEXT/JSON rather than a join table because reads are
            "the whole list per profile" and the cardinality is small
            (libraries are operator-managed, not user-generated).
            Default-deny: empty list means no access.
    """

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_kids: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    allowed_library_ids: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        server_default="[]",
    )


__all__ = ["ProfileModel"]
