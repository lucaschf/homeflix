"""Application settings using Pydantic Settings.

Settings are loaded from environment variables and .env file.
"""

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    media_directories: list[str] = Field(
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
    hls_cache_max_size_mb: int = Field(
        default=5120,
        description="Maximum HLS cache size in megabytes. When exceeded, "
        "the least-recently-accessed buckets are deleted until the "
        "cache fits. Default 5 GB.",
    )

    avatar_storage_subdir: str = Field(
        default=".homeflix/avatars",
        description="Subdirectory (relative to ``thumbnails_directory``) "
        "where uploaded profile avatars are stored. The subdirectory is "
        "created on first upload; the operator can change this without "
        "manual filesystem migration as long as the new path is empty.",
    )
    avatar_max_size_mb: int = Field(
        default=2,
        ge=1,
        le=20,
        description="Maximum accepted upload size for a profile avatar, "
        "in megabytes. Uploads above this cap are rejected with HTTP 413 "
        "before the image is decoded. Default 2 MB is comfortably above "
        "what a phone camera produces after the browser-side compression "
        "and well below what a laptop would happily upload over a slow "
        "connection.",
    )
    avatar_size_pixels: int = Field(
        default=256,
        ge=64,
        le=1024,
        description="Final square side length (in pixels) of the resized "
        "avatar. The uploaded image is centre-cropped to a square and "
        "scaled to this size before being persisted as WebP. 256 is the "
        "size the picker / AccountMenu render at 1x; bumping it would "
        "let those surfaces render crisper at 2x / 3x pixel density.",
    )

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
    # Scheduler / background jobs
    # =========================================================================
    # All scheduler / thumbnail-backfill / intro-detection tunables moved
    # to ``app_settings`` (ADR-013 phase 2). Set them via the admin
    # panel or ``UPDATE app_settings SET value_json=...`` for ops
    # overrides. Setting the legacy ``SCHEDULER_*``, ``THUMBNAIL_BACKFILL_*``
    # or ``INTRO_DETECTION_*`` env vars now has no effect — startup
    # warns about each one it sees (see ``main.py``).

    ffmpeg_threads: int | None = Field(
        default=None,
        ge=1,
        description="Maximum worker threads ffmpeg may use per invocation "
        "(applied as ``-threads N`` on every ffmpeg call). ``None`` (the "
        "default) leaves ffmpeg in 'auto' mode, which uses every logical "
        "core. Set this to roughly ``cpu_count // 2`` to cap transcoding "
        "to ~50%% of the host. Caps parallelism, not absolute CPU — there "
        "is no portable hard cap; use cgroups or equivalent if you need "
        "one. Applies to HLS transcoding, subtitle extraction, and "
        "scrub-preview sprite generation.",
    )

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
    supported_locales: list[str] = Field(default=["en", "pt-BR"])

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
