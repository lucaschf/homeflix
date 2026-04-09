"""Series DTOs for application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.media.application.dtos.media_file_dtos import MediaFileOutput


@dataclass(frozen=True)
class EpisodeOutput:
    """Output representation of an Episode.

    Attributes:
        id: External episode ID (epi_xxx), None if not yet persisted.
        episode_number: Episode number within the season.
        title: Episode title.
        synopsis: Episode synopsis (optional).
        duration_seconds: Duration in seconds.
        duration_formatted: Duration as HH:MM:SS.
        file_path: Path to video file (None if no primary file).
        file_size: File size in bytes (None if no primary file).
        resolution: Video resolution (None if no primary file).
        thumbnail_path: Path to thumbnail (optional).
        air_date: Original air date (optional, ISO format).
    """

    id: str | None
    episode_number: int
    title: str
    synopsis: str | None
    duration_seconds: int
    duration_formatted: str
    file_path: str | None
    file_size: int | None
    resolution: str | None
    files: list[MediaFileOutput]
    thumbnail_path: str | None
    air_date: str | None


@dataclass(frozen=True)
class SeasonOutput:
    """Output representation of a Season.

    Attributes:
        id: External season ID (ssn_xxx), None if not yet persisted.
        season_number: Season number (0 for specials).
        title: Season title (optional).
        synopsis: Season synopsis (optional).
        poster_path: Path to poster (optional).
        air_date: First air date (optional, ISO format).
        episode_count: Number of episodes.
        episodes: List of episodes in this season.
    """

    id: str | None
    season_number: int
    title: str | None
    synopsis: str | None
    poster_path: str | None
    air_date: str | None
    episode_count: int
    episodes: list[EpisodeOutput]


@dataclass(frozen=True)
class SeriesOutput:
    """Output representation of a Series with full hierarchy.

    Contains all series fields including nested seasons and episodes.

    Attributes:
        id: External series ID (ser_xxx).
        title: Display title.
        original_title: Original language title (optional).
        start_year: First season year.
        end_year: Final season year (None if ongoing).
        is_ongoing: Whether the series is still in production.
        synopsis: Series synopsis (optional).
        poster_path: Path to poster (optional).
        backdrop_path: Path to backdrop (optional).
        genres: List of genre strings.
        tmdb_id: TMDB external ID (optional).
        imdb_id: IMDB external ID (optional).
        season_count: Number of seasons.
        total_episodes: Total episode count.
        seasons: List of seasons with episodes.
        created_at: ISO timestamp of creation.
        updated_at: ISO timestamp of last update.
    """

    id: str
    title: str
    original_title: str | None
    start_year: int
    end_year: int | None
    is_ongoing: bool
    synopsis: str | None
    poster_path: str | None
    backdrop_path: str | None
    genres: list[str]
    content_rating: str | None
    tmdb_id: int | None
    imdb_id: str | None
    season_count: int
    total_episodes: int
    seasons: list[SeasonOutput]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SeriesSummaryOutput:
    """Summary representation of a Series for list views.

    Contains essential fields for displaying series in a grid/list.
    Does NOT include full episode data to keep response lightweight.

    Attributes:
        id: External series ID.
        title: Display title.
        start_year: First season year.
        end_year: Final season year (None if ongoing).
        is_ongoing: Whether still in production.
        poster_path: Path to poster (optional).
        season_count: Number of seasons.
        total_episodes: Total episode count.
        genres: List of genre strings.
    """

    id: str
    title: str
    start_year: int
    end_year: int | None
    is_ongoing: bool
    synopsis: str | None
    poster_path: str | None
    backdrop_path: str | None
    season_count: int
    total_episodes: int
    genres: list[str]


@dataclass(frozen=True)
class GetSeriesByIdInput:
    """Input for GetSeriesByIdUseCase.

    Attributes:
        series_id: External ID of the series (ser_xxx format).
        lang: Language code for localized metadata.
    """

    series_id: str
    lang: str = "en"


@dataclass(frozen=True)
class ListSeriesInput:
    """Input for ListSeriesUseCase.

    Attributes:
        limit: Maximum number of series to return (optional, default: all).
        lang: Language code for localized metadata.
    """

    limit: int | None = None
    lang: str = "en"


@dataclass(frozen=True)
class ListSeriesOutput:
    """Output for ListSeriesUseCase.

    Attributes:
        series: List of series summaries.
        total_count: Total number of series in the library.
    """

    series: list[SeriesSummaryOutput]
    total_count: int


__all__ = [
    "EpisodeOutput",
    "GetSeriesByIdInput",
    "ListSeriesInput",
    "ListSeriesOutput",
    "SeasonOutput",
    "SeriesOutput",
    "SeriesSummaryOutput",
]
