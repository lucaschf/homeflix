"""Series aggregate root."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from pydantic import Field, field_validator, model_validator

from src.building_blocks.domain import AggregateRoot
from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.modules.media.domain.events import MediaCreatedEvent
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects import (
    CastMember,
    ContentRating,
    Genre,
    ImageUrl,
    ImdbId,
    LocalizedField,
    LocalizedMetadata,
    SeasonNumber,
    SeriesId,
    Title,
    TmdbId,
    Year,
)
from src.shared_kernel.value_objects.media_type import MediaType

if TYPE_CHECKING:
    from src.modules.media.domain.entities.season import Season


class Series(AggregateRoot[SeriesId]):
    """Series aggregate root containing Seasons and Episodes.

    Represents a TV series with its metadata and season/episode structure.
    This is the main entry point for series-related operations.

    Example:
        >>> series = Series.create(
        ...     title="Breaking Bad",
        ...     start_year=2008,
        ... )
    """

    # Identity
    id: SeriesId | None = Field(default=None)

    # Library scoping (the lib_xxx external id of the owning Library;
    # held as ``str`` because Library lives in another bounded context
    # and ADR-008 forbids the cross-BC import). Episodes inherit
    # scoping through their parent Series — they do not carry their
    # own ``library_id``.
    library_id: str

    # Core info
    title: Title
    original_title: Title | None = None
    start_year: Year
    end_year: Year | None = None  # None means still ongoing
    synopsis: str | None = Field(default=None, max_length=10000)

    # Images
    poster_path: ImageUrl | None = None
    backdrop_path: ImageUrl | None = None
    logo_path: ImageUrl | None = None

    # Categorization
    genres: list[Genre] = Field(default_factory=list)
    content_rating: ContentRating | None = None
    trailer_url: str | None = None

    # Credits (top-billed cast pulled from TMDB during enrichment).
    # Mirrors Movie.cast so the detail page can render the same
    # actor cards on series and movies, and so the actor browse page
    # can later filter on series cast as well.
    cast: list[CastMember] = Field(default_factory=list)

    # Localized metadata
    localized: LocalizedMetadata = Field(default_factory=LocalizedMetadata)

    # External IDs
    tmdb_id: TmdbId | None = None
    imdb_id: ImdbId | None = None

    # Set true when the series needs an enrichment review — either an
    # enrichment attempt couldn't resolve a TMDB match or an operator
    # flagged the result as wrong (matched the wrong title). Read by
    # the admin "needs review" listing so the operator can relink
    # manually. Cleared on the next successful enrichment.
    needs_enrichment_review: bool = False

    # Composition
    seasons: list[Season] = Field(default_factory=list)

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | SeriesId | None) -> SeriesId | None:
        """Convert string to SeriesId if needed."""
        if v is None:
            return None

        return SeriesId(v) if isinstance(v, str) else v

    # -- Localized accessors ---------------------------------------------------

    def get_title(self, lang: str = "en") -> str:
        """Get title in the requested language, falling back to default."""
        return self.localized.text(LocalizedField.TITLE, lang) or self.title.value

    def get_synopsis(self, lang: str = "en") -> str | None:
        """Get synopsis in the requested language, falling back to default."""
        return self.localized.text(LocalizedField.SYNOPSIS, lang) or self.synopsis

    def get_genres(self, lang: str = "en") -> list[str]:
        """Get genres in the requested language, falling back to default."""
        loc_genres = self.localized.genres(lang)
        return list(loc_genres) if loc_genres else [g.value for g in self.genres]

    def get_logo_path(self, lang: str = "en") -> str | None:
        """Get title-logo URL for the requested language.

        Falls back to ``self.logo_path`` (the language at enrich time,
        typically en) when the language has no localized override —
        mirroring how ``get_title`` / ``get_synopsis`` behave so the
        UI sees a consistent "best available" graphic per language.
        """
        return self.localized.text(LocalizedField.LOGO_PATH, lang) or (
            self.logo_path.value if self.logo_path else None
        )

    def get_poster_path(self, lang: str = "en") -> str | None:
        """Get poster URL for the requested language, falling back to default.

        Mirrors ``get_logo_path``: returns the locale's localized poster
        when present, else the global (English base) ``poster_path``.
        """
        return self.localized.text(LocalizedField.POSTER_PATH, lang) or (
            self.poster_path.value if self.poster_path else None
        )

    def get_backdrop_path(self, lang: str = "en") -> str | None:
        """Get backdrop URL for the requested language, falling back to default."""
        return self.localized.text(LocalizedField.BACKDROP_PATH, lang) or (
            self.backdrop_path.value if self.backdrop_path else None
        )

    @model_validator(mode="after")
    def validate_year_range(self) -> Series:
        """Ensure end_year >= start_year if end_year is set."""
        if self.end_year is not None and self.end_year < self.start_year:
            raise ValueError("end_year cannot be before start_year")
        return self

    @property
    def season_count(self) -> int:
        """Return the number of seasons.

        Returns:
            The count of seasons.
        """
        return len(self.seasons)

    @property
    def total_episodes(self) -> int:
        """Return total episode count across all seasons.

        Returns:
            The total number of episodes in all seasons.
        """
        return sum(s.episode_count for s in self.seasons)

    @property
    def intro_marked_count(self) -> int:
        """Return the number of episodes that have an intro marker set.

        Counts episodes (across all seasons) whose intro span has been
        recorded, whether auto-detected or set manually. Lets the admin
        UI show per-series "skip intro" coverage without loading each
        season's detail.

        Returns:
            The count of episodes with an intro marker.
        """
        return sum(
            1 for season in self.seasons for episode in season.episodes if episode.intro is not None
        )

    @property
    def intro_resolved_count(self) -> int:
        """Return the number of episodes whose intro question is settled.

        Counts episodes with a marker *plus* those confirmed to have no
        opening sequence. This is the coverage number the admin UI
        should track: ``intro_marked_count`` alone can never reach the
        episode total on a series where some episodes genuinely have no
        intro, so such a series would read as forever incomplete.

        Returns:
            The count of episodes that no longer need review.
        """
        return sum(
            1 for season in self.seasons for episode in season.episodes if episode.intro_resolved
        )

    @property
    def is_ongoing(self) -> bool:
        """Check if the series is still ongoing.

        Returns:
            True if series has no end_year.
        """
        return self.end_year is None

    def with_enrichment_review_flagged(self) -> Self:
        """Return a copy flagged for manual enrichment review.

        Used when an operator decides the current metadata is wrong
        (the enrichment matched the wrong title) and wants the series
        back in the admin review queue. Idempotent — returns ``self``
        when the flag is already set so no spurious ``updated_at`` bump
        happens. The flag is cleared on the next successful enrichment
        (see ``EnrichSeriesMetadataUseCase``).

        Returns:
            A new Series with ``needs_enrichment_review=True``, or
            ``self`` if it was already flagged.
        """
        if self.needs_enrichment_review:
            return self
        return self.with_updates(needs_enrichment_review=True)

    def _ensure_owns(self, season: Season) -> None:
        """Validate the season belongs to this series.

        Raises:
            BusinessRuleViolationException: If season series_id doesn't match.
        """
        if season.series_id != self.id:
            raise BusinessRuleViolationException(
                message="Season series_id must match Series id",
                rule_code=MediaRuleCodes.SEASON_SERIES_MISMATCH,
            )

    def with_season(self, season: Season) -> Self:
        """Return a copy with the season added.

        Args:
            season: The season to add.

        Returns:
            A new Series with the season added, or self if already present.

        Raises:
            BusinessRuleViolationException: If season series_id doesn't match.
        """
        self._ensure_owns(season)
        if season in self.seasons:
            return self
        return self.with_updates(seasons=[*self.seasons, season])

    def with_season_upserted(self, season: Season) -> Self:
        """Return a copy with the season added or replaced by its number.

        Unlike :meth:`with_season` (a no-op when the season is already
        present), this replaces any existing season that shares the same
        ``season_number`` — the scanner uses it to fold a refreshed season
        back into the series while keeping the "one season per number"
        invariant owned by the series. Always returns a new instance (it
        never short-circuits to ``self``), since the replacement may carry
        a refreshed season under the same number.

        Args:
            season: The season to upsert.

        Returns:
            A new Series with the season inserted or replaced.

        Raises:
            BusinessRuleViolationException: If season series_id doesn't
                match this series.
        """
        self._ensure_owns(season)
        seasons = list(self.seasons)
        for idx, existing in enumerate(seasons):
            if existing.season_number == season.season_number:
                seasons[idx] = season
                break
        else:
            seasons.append(season)
        return self.with_updates(seasons=seasons)

    def get_season(self, season_number: SeasonNumber | int) -> Season | None:
        """Find a season by its number.

        Args:
            season_number: The season number to find.

        Returns:
            The Season if found, None otherwise.
        """
        needle = (
            season_number
            if isinstance(season_number, SeasonNumber)
            else SeasonNumber(season_number)
        )
        return next(
            (season for season in self.seasons if season.season_number == needle),
            None,
        )

    @classmethod
    def create(
        cls,
        title: str | Title,
        start_year: int | Year,
        library_id: str,
        **kwargs: Any,
    ) -> Series:
        """Factory method with automatic ID generation.

        Args:
            title: Series title.
            start_year: First season year.
            library_id: External id (``lib_xxx``) of the owning Library.
            **kwargs: Additional optional fields.

        Returns:
            A new Series instance with generated ID.
        """
        series_id = SeriesId.generate()

        if isinstance(title, str):
            title = Title(title)
        if isinstance(start_year, int):
            start_year = Year(start_year)

        series = cls(
            id=series_id,
            library_id=library_id,
            title=title,
            start_year=start_year,
            **kwargs,
        )
        series.add_event(MediaCreatedEvent(media_id=series_id, media_type=MediaType.SERIES))
        return series


__all__ = ["Series"]
