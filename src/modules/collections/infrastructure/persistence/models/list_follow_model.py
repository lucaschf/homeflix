"""ListFollow ORM model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class ListFollowModel(Base):
    """SQLAlchemy model for ``ListFollow``.

    Maps to the ``list_follows`` table. Each row is one profile's live
    subscription to a shared custom list — the follower side of the
    share/follow feature. Mirrors ``CatalogSubscriptionModel``: the
    referenced list travels as its external id string (no cross-table
    FK), and ``(follower_profile_id, list_id)`` is unique among live
    rows via a partial unique index declared in the alembic migration,
    keeping a repeat follow idempotent.

    Attributes:
        follower_profile_id: External id (``prf_xxx``) of the following
            profile. Indexed for the "my followed lists" read.
        list_id: External id (``lst_xxx``) of the followed
            ``CustomList``. Indexed for the owner-side cleanup that
            drops every follow of a list on delete/revoke.
    """

    follower_profile_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    list_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<ListFollowModel(id={self.id}, "
            f"follower_profile_id={self.follower_profile_id!r}, list_id={self.list_id!r})>"
        )


__all__ = ["ListFollowModel"]
