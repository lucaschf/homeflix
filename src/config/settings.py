"""Application settings using Pydantic Settings.

Settings are loaded from environment variables and .env file.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # Internationalization
    # =========================================================================

    default_locale: str = Field(default="en")
    supported_locales: list[str] = Field(default=["en", "pt-BR"])

    @field_validator("supported_locales", mode="before")
    @classmethod
    def parse_locales(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated locales string to list."""
        return [loc.strip() for loc in v.split(",")] if isinstance(v, str) else v

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
