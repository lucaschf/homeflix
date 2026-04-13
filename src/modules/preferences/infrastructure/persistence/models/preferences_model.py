"""User preferences ORM model."""

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from src.config.persistence.base import Base


class PreferencesModel(Base):
    """SQLAlchemy model for user playback preferences.

    Singleton-per-user design: there's exactly one row per
    ``user_key``. Until an auth system lands the only key is
    ``"default"`` — all browser sessions share the same prefs.

    Maps to the ``preferences`` table.
    """

    user_key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        default="default",
    )
    audio_lang: Mapped[str] = mapped_column(String(10), nullable=False, default="pt-BR")
    subtitle_lang: Mapped[str] = mapped_column(String(10), nullable=False, default="pt-BR")
    subtitle_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="foreignOnly")
    default_quality: Mapped[str] = mapped_column(String(20), nullable=False, default="best")
    speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


__all__ = ["PreferencesModel"]
