"""CatalogSubscription ORM model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class CatalogSubscriptionModel(Base):
    """SQLAlchemy model for ``CatalogSubscription``.

    Maps to the ``catalog_subscriptions`` table. Each row is one
    user's opt-in to be notified when a queued title arrives
    (ADR-022) — the per-user fanout layer that ``CatalogRequest``
    (one row per title) deliberately doesn't carry.

    ``(request_id, user_id)`` is unique among non-deleted rows so a
    repeat "Avisar quando chegar" stays idempotent; that partial
    unique index lives in the alembic migration only (the dev
    auto-create path covers the per-column lookups via the indexes
    below).

    Attributes:
        request_id: External id (``req_xxx``) of the parent
            ``CatalogRequest`` this subscription belongs to. Plain
            indexed string, mirroring how the BC references user /
            collection ids — no cross-table foreign key.
        user_id: External id (``usr_xxx``) of the subscriber to ping
            on arrival.
    """

    request_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<CatalogSubscriptionModel(id={self.id}, "
            f"request_id={self.request_id!r}, user_id={self.user_id!r})>"
        )


__all__ = ["CatalogSubscriptionModel"]
