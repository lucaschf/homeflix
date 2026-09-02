"""User preferences ORM model."""

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class PreferencesModel(Base):
    """SQLAlchemy model for per-profile playback preferences.

    Singleton-per-profile design: there's exactly one row per
    ``profile_id``. The unique index on ``profile_id`` enforces it
    at the DB level so a race between two concurrent first-saves
    can't materialise two rows.

    Maps to the ``preferences`` table.
    """

    profile_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )
    audio_lang: Mapped[str] = mapped_column(String(10), nullable=False, default="pt-BR")
    subtitle_lang: Mapped[str] = mapped_column(String(10), nullable=False, default="pt-BR")
    subtitle_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="foreignOnly")
    default_quality: Mapped[str] = mapped_column(String(20), nullable=False, default="best")
    speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    subtitle_color: Mapped[str] = mapped_column(String(32), nullable=False, default="#FFFFFF")
    subtitle_background: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="rgba(0, 0, 0, 0.75)",
    )
    subtitle_font_size: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    subtitle_text_edge: Mapped[str] = mapped_column(String(10), nullable=False, default="shadow")
    intro_skip_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    credits_skip_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")


__all__ = ["PreferencesModel"]
