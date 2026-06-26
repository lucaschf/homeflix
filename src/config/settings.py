"""Application settings using Pydantic Settings.

Settings are loaded from environment variables and .env file.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_PLACEHOLDER_SECRET_KEY = "CHANGE-ME-IN-PRODUCTION"  # — sentinel literal, not a secret


class Settings(BaseSettings):  # type: ignore[misc]
    """Application settings.

    All settings can be overridden via environment variables.
    Environment variables are case-insensitive.

    Example:
        # .env file
        DATABASE_URL=sqlite+aiosqlite:///./homeflix.db
        TMDB_API_KEY=your_key_here

        # Usage
        >>> settings = Settings()
        >>> settings.database_url
        'sqlite+aiosqlite:///./homeflix.db'
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # Application
    # =========================================================================

    app_name: str = Field(default="HomeFlix")
    app_env: str = Field(default="development")
    debug: bool = Field(default=True)
    log_level: str = Field(default="DEBUG")

    # =========================================================================
    # Server
    # =========================================================================

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8005)
    allowed_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:5173"])

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated origins string to list."""
        return [origin.strip() for origin in v.split(",")] if isinstance(v, str) else v

    # =========================================================================
    # Database
    # =========================================================================

    database_url: str = Field(
        default="sqlite+aiosqlite:///./homeflix.db",
        description="Database connection URL",
    )

    # =========================================================================
    # Media
    # =========================================================================

    # ``NoDecode`` skips pydantic-settings' default JSON decoding of
    # list fields so the comma-separated ``.env`` value reaches the
    # ``parse_media_dirs`` validator below instead of failing as
    # invalid JSON.
    media_directories: Annotated[list[str], NoDecode] = Field(
        default=[],
        description="Directories to scan for media files",
    )
    thumbnails_directory: str = Field(
        default="./thumbnails",
        description="Directory to store generated thumbnails",
    )
    hls_cache_directory: str = Field(
        default="./hls_cache",
        description="Directory to store cached HLS segments",
    )

    # ``hls_cache_max_size_mb`` and the ``avatar_*`` knobs moved to
    # ``app_settings`` in ADR-013 phase 3. Set them via the admin
    # panel or ``UPDATE app_settings SET value_json=...``. The legacy
    # env vars no longer take effect — startup warns if any of them
    # are still set.

    @field_validator("media_directories", mode="before")
    @classmethod
    def parse_media_dirs(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated directories string to list."""
        if isinstance(v, str):
            return [d.strip() for d in v.split(",")] if v else []
        return v

    # =========================================================================
    # External APIs
    # =========================================================================

    tmdb_api_key: str | None = Field(
        default=None,
        description="The Movie Database API key",
    )
    tmdb_base_url: str = Field(
        default="https://api.themoviedb.org/3",
        description="TMDB API base URL",
    )

    omdb_api_key: str | None = Field(
        default=None,
        description="OMDb API key (optional fallback)",
    )

    # =========================================================================
    # Scheduler / background jobs / streaming / avatar
    # =========================================================================
    # All operational tunables (scheduler, thumbnail backfill, intro
    # detection, streaming, avatar) moved to ``app_settings`` across
    # ADR-013 phases 2 and 3. Set them via the admin panel or
    # ``UPDATE app_settings SET value_json=...`` for ops overrides.
    # The legacy ``SCHEDULER_*``, ``THUMBNAIL_BACKFILL_*``,
    # ``INTRO_DETECTION_*``, ``FFMPEG_THREADS``,
    # ``HLS_CACHE_MAX_SIZE_MB``, and ``AVATAR_*`` env vars now have
    # no effect — startup warns about each one it sees
    # (see ``main.py``).

    # =========================================================================
    # Identity / Auth (see ADR-010 / ADR-011)
    # =========================================================================

    secret_key: SecretStr = Field(
        default=SecretStr(_PLACEHOLDER_SECRET_KEY),
        description="Secret used by FastAPI Users for password-reset and "
        "email-verification token signing. The session cookie itself is "
        "opaque DB-backed (per ADR-011), not signed, so this only affects "
        "those future flows. Wrapped in ``SecretStr`` so Pydantic does "
        "not echo the value in ``repr``/``model_dump`` output. Replaced "
        "in production via env var; the placeholder is rejected by the "
        "production-environment validator below.",
    )
    session_lifetime_seconds: int = Field(
        default=60 * 60 * 24 * 90,  # 90 days — per ADR-011 (fixed, no slide)
        ge=60,
        description="Fixed lifetime of a session cookie / DB row before it "
        "expires. No rolling refresh — DatabaseStrategy from FastAPI Users "
        "doesn't support sliding expiration natively.",
    )
    session_cookie_secure: bool = Field(
        default=False,
        description="Set the Secure flag on the session cookie (HTTPS only). "
        "Defaults False so dev over plain HTTP still works; the "
        "production-environment validator below refuses to start unless "
        "this is True (or a manual override is provided).",
    )
    session_cookie_name: str = Field(default="homeflix_session")

    # =========================================================================
    # Internationalization
    # =========================================================================

    default_locale: str = Field(default="en")
    # ``NoDecode`` lets the ``parse_locales`` validator handle the
    # comma-separated ``.env`` form (e.g. ``en,pt-BR``); without it
    # pydantic-settings tries to JSON-decode the value and fails.
    supported_locales: Annotated[list[str], NoDecode] = Field(default=["en", "pt-BR"])

    @field_validator("supported_locales", mode="before")
    @classmethod
    def parse_locales(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated locales string to list."""
        return [loc.strip() for loc in v.split(",")] if isinstance(v, str) else v

    @model_validator(mode="after")
    def reject_insecure_production_config(self) -> Self:
        """Refuse to start in production with security-critical defaults.

        Cross-field check that runs once per ``Settings`` instance after
        all individual field validation. Caught at construction so the
        process exits before the unsafe config can take effect.
        """
        if self.app_env == "production":
            if self.secret_key.get_secret_value() == _PLACEHOLDER_SECRET_KEY:
                raise ValueError(
                    "secret_key is still the development placeholder; "
                    "set SECRET_KEY to a strong unique value before "
                    "running in production.",
                )
            if not self.session_cookie_secure:
                raise ValueError(
                    "session_cookie_secure must be True in production "
                    "(HTTPS-only cookie). Set SESSION_COOKIE_SECURE=true "
                    "or run behind a TLS-terminating reverse proxy.",
                )
        return self

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"

    @property
    def thumbnails_path(self) -> Path:
        """Get thumbnails directory as a Path object."""
        return Path(self.thumbnails_directory)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Singleton Settings instance.
    """
    return Settings()
