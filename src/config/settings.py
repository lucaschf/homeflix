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
    # Scheduler
    # =========================================================================

    scheduler_enabled: bool = Field(
        default=True,
        description="Enable the background scheduler (library scans, etc.).",
    )
    scheduler_reconcile_interval_minutes: int = Field(
        default=5,
        ge=1,
        description="How often the scheduler re-reads libraries from the "
        "database to sync cron jobs with configured schedules.",
    )

    thumbnail_backfill_enabled: bool = Field(
        default=True,
        description="Enable the periodic job that fills in scrub-preview "
        "thumbnails for movies and episodes that don't have one yet.",
    )
    thumbnail_backfill_batch_size: int = Field(
        default=10,
        ge=1,
        description="Maximum number of media items processed per backfill "
        "tick. Lower values reduce CPU spikes; higher values catch up "
        "faster on a large catalog.",
    )
    thumbnail_backfill_interval_minutes: int = Field(
        default=20,
        ge=1,
        description="How often the thumbnail backfill job runs.",
    )
    thumbnail_backfill_subdir: str = Field(
        default=".homeflix/thumbnails",
        description="Subdirectory (relative to each media file's parent "
        "folder) where backfilled sprite + VTT files are written.",
    )

    intro_detection_enabled: bool = Field(
        default=False,
        description="Enable the periodic intro-detection job that locates "
        "the shared opening sequence for each season via Chromaprint "
        "audio fingerprinting. Off by default because it requires the "
        "``fpcalc`` binary on PATH; turn it on once Chromaprint is "
        "installed (``apt install libchromaprint-tools`` / "
        "``brew install chromaprint``).",
    )
    intro_detection_batch_size: int = Field(
        default=1,
        ge=1,
        description="Maximum number of seasons processed per detection "
        "tick. Each season triggers ffmpeg + fpcalc per episode, so "
        "values above 2 can saturate the host on large seasons.",
    )
    intro_detection_interval_minutes: int = Field(
        default=30,
        ge=1,
        description="How often the intro-detection job runs.",
    )
    intro_detection_audio_window_seconds: int = Field(
        default=600,
        ge=60,
        description="How many seconds of leading audio to analyse per "
        "episode. 600s (10 min) covers all common cold-open + intro "
        "lengths; trimming this lower speeds up the job at the cost "
        "of missing intros that start late.",
    )
    intro_detection_min_confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum detector confidence (in ``[0.0, 1.0]``) "
        "required before an auto-detected intro is persisted. Confidence "
        "is the fraction of peer episodes whose fingerprint agreed "
        "with the candidate marker.",
    )
    intro_detection_max_hash_hamming: int = Field(
        default=10,
        ge=0,
        le=32,
        description="Per-hash hamming-distance ceiling (out of 32 bits) "
        "considered a 'match' between two episode fingerprints. Lower "
        "values reject more borderline hashes — useful when detections "
        "overshoot into shared underscore music; higher values absorb "
        "more chromaprint noise.",
    )
    intro_detection_tolerance_hashes: int = Field(
        default=2,
        ge=0,
        description="How many CONSECUTIVE non-matching hashes a run "
        "can absorb before terminating. A fresh good hash resets the "
        "counter so isolated chromaprint noise is forgiven indefinitely.",
    )
    intro_detection_min_intro_seconds: float = Field(
        default=5.0,
        ge=0.0,
        description="Minimum intro length to accept. Shorter matches "
        "are dropped — usually they are recurring stingers / bumpers "
        "rather than the title sequence proper.",
    )
    intro_detection_max_intro_seconds: float = Field(
        default=120.0,
        ge=10.0,
        description="Hard cap on persisted intro length. Real intros "
        "rarely exceed two minutes; longer detections almost always "
        "include shared underscore that bleeds past the title sequence "
        "and should be truncated to avoid skipping into the episode.",
    )

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
