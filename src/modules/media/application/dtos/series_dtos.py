"""Series DTOs for application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.building_blocks.application.pagination import DEFAULT_PAGE_SIZE

if TYPE_CHECKING:
    from src.modules.media.application.dtos.intro_dtos import IntroMarkerOutput
    from src.modules.media.application.dtos.media_file_dtos import MediaFileOutput
    from src.modules.media.application.dtos.movie_dtos import CastMemberOutput


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
        scrub_preview_path: Absolute filesystem path to the scrub-preview
            VTT, or ``None`` until the backfill job generates it.
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
    scrub_preview_path: str | None
    air_date: str | None
    intro: IntroMarkerOutput | None = None
    progress_percentage: float | None = None
    position_seconds: int | None = None
    watch_status: str | None = None
    last_watched_at: str | None = None


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
        logo_path: URL of the title-logo image (transparent PNG)
            populated from TMDB during enrich, ``None`` if not
            available. Used by the hero/detail UI to render the title
            as a graphic.
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
    logo_path: str | None
    genres: list[str]
    content_rating: str | None
    trailer_url: str | None
    tmdb_id: int | None
    imdb_id: str | None
    season_count: int
    total_episodes: int
    seasons: list[SeasonOutput]
    cast: list[CastMemberOutput]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SeriesSummaryOutput:
    """Summary representation of a Series for list views.

    Contains essential fields for displaying series in a grid/list.
    Does NOT include full episode data to keep response lightweight.
    The admin Catalog table reads the same shape; the trailing
    operator-facing fields (``library_id``, ``tmdb_id``, ``imdb_id``)
    are ignored by user-facing surfaces.

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
        library_id: External library id (``lib_xxx``) owning the
            series. Used by the admin Catalog "Library" column.
        tmdb_id: TMDB primary key, or ``None`` for un-enriched
            series.
        imdb_id: IMDb id (``tt…``), or ``None``.
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
    library_id: str
    tmdb_id: int | None
    imdb_id: str | None


@dataclass(frozen=True)
class DeleteSeriesInput:
    """Input for ``DeleteSeriesUseCase``.

    Attributes:
        series_id: External ID of the series (``ser_xxx``).
    """

    series_id: str


@dataclass(frozen=True)
class GetSeriesByIdInput:
    """Input for GetSeriesByIdUseCase.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case looks
            up the per-profile library ACL through
            ``ProfileLibraryAccessPort`` and restricts the lookup to
            those libraries — a row outside the ACL surfaces as
            ``ResourceNotFoundException`` (404).
        series_id: External ID of the series (ser_xxx format).
        lang: Language code for localized metadata.
    """

    profile_id: str
    series_id: str
    lang: str = "en"


@dataclass(frozen=True)
class ListSeriesInput:
    """Input for ListSeriesUseCase.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case
            consults ``ProfileLibraryAccessPort`` and restricts the
            page to libraries the profile may see; a deny-all profile
            yields an empty page without opening a UoW.
        cursor: Opaque pagination cursor from the previous page's
            ``next_cursor``. ``None`` (or any invalid token) starts at
            the first page.
        limit: Page size. Routes clamp this to ``[1, MAX_PAGE_SIZE]``
            before constructing the input.
        include_total: When ``True`` the use case asks the repository
            for an extra ``COUNT(*)`` so ``total_count`` is populated.
            Defaults to ``False`` for performance.
        lang: Language code for localized metadata.
    """

    profile_id: str
    cursor: str | None = None
    limit: int = DEFAULT_PAGE_SIZE
    include_total: bool = False
    lang: str = "en"
    # Optional filters used by the admin Catalog page; ``None`` on
    # the user-facing list means "no extra constraint".
    library_id: str | None = None
    has_tmdb_id: bool | None = None


@dataclass(frozen=True)
class ListSeriesOutput:
    """Output for ListSeriesUseCase.

    Attributes:
        series: List of series summaries on this page.
        next_cursor: Opaque token to pass back as ``cursor`` on the
            next request, or ``None`` when there are no more pages.
        has_more: Convenience flag — equivalent to
            ``next_cursor is not None`` but explicit.
        total_count: Total number of (non-deleted) series in the
            library, or ``None`` when the caller did not request it
            via ``include_total``.
    """

    series: list[SeriesSummaryOutput]
    next_cursor: str | None
    has_more: bool
    total_count: int | None = None


@dataclass(frozen=True)
class ListRecentlyAddedSeriesInput:
    """Input for ``ListRecentlyAddedSeriesUseCase``.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case
            consults ``ProfileLibraryAccessPort`` and restricts the
            top-N to libraries the profile may see; a deny-all
            profile yields an empty list without opening a UoW.
        limit: Maximum number of series to return. Routes clamp this
            to a sane upper bound before constructing the input.
        lang: Language code for localized metadata.
    """

    profile_id: str
    limit: int = 20
    lang: str = "en"


@dataclass(frozen=True)
class ListRecentlyAddedSeriesOutput:
    """Output for ``ListRecentlyAddedSeriesUseCase``.

    Plain top-N projection — no cursor, no ``has_more``. Mirror of
    ``ListRecentlyAddedMoviesOutput`` for the series side of the
    home-page carousel.

    Attributes:
        series: List of series summaries, newest first.
    """

    series: list[SeriesSummaryOutput]


__all__ = [
    "EpisodeOutput",
    "GetSeriesByIdInput",
    "ListRecentlyAddedSeriesInput",
    "ListRecentlyAddedSeriesOutput",
    "ListSeriesInput",
    "ListSeriesOutput",
    "SeasonOutput",
    "SeriesOutput",
    "SeriesSummaryOutput",
]
