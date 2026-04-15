"""Library ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.config.persistence.base import Base


class LibraryModel(Base):
    """SQLAlchemy model for Library aggregate.

    Maps to the 'libraries' table (auto-generated from class name via
    ``Base.__tablename__``).  Complex nested fields (paths, settings,
    metadata providers) are stored as JSON text columns — they're read
    and written as a whole by the mapper, never queried individually,
    so a JSON column is a better fit than a normalized join table.

    Attributes:
        name: User-friendly library name.
        library_type: One of ``movies``, ``series``, ``mixed``.
        paths: JSON array of directory paths included in this library.
        language: ISO 639-1 language code for the library's primary
            content language (e.g. ``en``, ``pt``).
        metadata_providers: JSON array of
            ``{provider, priority, enabled}`` objects.
        scan_schedule: Optional 5-field cron pattern.
        settings: JSON blob of ``LibrarySettings`` (preferred audio/sub
            language, subtitle mode, thumbnails, etc.).
    """

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    library_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    paths: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    metadata_providers: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    scan_schedule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settings: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<LibraryModel(id={self.id}, external_id={self.external_id!r}, "
            f"name={self.name!r}, type={self.library_type!r})>"
        )


__all__ = ["LibraryModel"]
