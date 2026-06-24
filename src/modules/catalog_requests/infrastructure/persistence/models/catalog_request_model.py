"""CatalogRequest ORM model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class CatalogRequestModel(Base):
    """SQLAlchemy model for ``CatalogRequest``.

    Maps to the ``catalog_requests`` table. Each row represents a
    user-initiated request to add a TMDB title to the catalog.

    The ``(tmdb_id, media_type)`` pair is unique among non-deleted
    rows so the API stays naturally idempotent on repeated submits.

    Attributes:
        tmdb_id: TMDB numeric id of the requested title.
        media_type: ``"movie"`` or ``"series"``.
        title: Snapshot of the TMDB title at the moment the request
            was registered, so the admin queue can render the title
            inline without re-querying TMDB. ``None`` on rows created
            before this column existed (the admin page falls back to
            the bare ``tmdb/<id>`` link in that case).
        requester_user_id: External id (``usr_xxx``) of the user who
            registered the request. Layer B of the catalog-request
            arrival flow uses this anchor to send the "title is
            now available" notification to the right inbox instead
            of broadcasting across the household. ``None`` on legacy
            rows or programmatic seeds — those stay anonymous and
            never produce a notification.
        collection_tmdb_id: Originating TMDB collection id, if any.
        source: ``"user"`` when a member asked for the title,
            ``"household"`` when the system seeded it (ADR-022).
        notify_on_arrival: Whether the user opted in to a "title
            now available" notification.
        requested_at: First-time creation timestamp (separate from
            ``created_at`` because we may later support deduplicated
            re-requests that bump ``updated_at`` without changing the
            original request time).
        fulfilled_at: Set when the title becomes locally available.
    """

    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requester_user_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    collection_tmdb_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="household",
        server_default="household",
    )
    notify_on_arrival: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Composite ``(tmdb_id, media_type)`` index lives in the alembic
    # migration only — declaring it here too would duplicate the
    # source of truth without buying anything (the dev auto-create
    # path already covers ``tmdb_id`` lookups via the per-column
    # index above; the composite is a prod query-tuning aid).

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<CatalogRequestModel(id={self.id}, tmdb_id={self.tmdb_id}, "
            f"media_type={self.media_type!r}, notify={self.notify_on_arrival})>"
        )


__all__ = ["CatalogRequestModel"]
