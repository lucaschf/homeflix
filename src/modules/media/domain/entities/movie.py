"""Movie aggregate root."""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, field_validator

from src.building_blocks.domain import AggregateRoot
from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.modules.media.domain.entities.file_variant_mixin import FileVariantMixin
from src.modules.media.domain.events import MediaCreatedEvent
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects import (
    CastMember,
    Collection,
    ContentRating,
    CreditsDetectionState,
    CreditsMarker,
    Duration,
    FilePath,
    Genre,
    ImageUrl,
    ImdbId,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    TmdbId,
    Year,
)
from src.shared_kernel.value_objects.media_type import MediaType


class Movie(FileVariantMixin, AggregateRoot[MovieId]):
    """Movie aggregate root.

    Represents a movie with its metadata and file variants.
    This is the main entry point for movie-related operations.

    Example:
        >>> movie = Movie.create(
        ...     title="Inception",
        ...     year=2010,
        ...     duration=8880,
        ...     file_path="/movies/inception.mkv",
        ...     file_size=4_000_000_000,
        ...     resolution="1080p",
        ... )
    """

    # Identity
    id: MovieId | None = Field(default=None)

    # Library scoping (the lib_xxx external id of the owning Library;
    # held as ``str`` because Library lives in another bounded context
    # and ADR-008 forbids the cross-BC import).
    library_id: str

    # Core info
    title: Title
    original_title: Title | None = None
    year: Year
    duration: Duration
    synopsis: str | None = Field(default=None, max_length=10000)
    tagline: str | None = Field(default=None, max_length=500)

    # Images
    poster_path: ImageUrl | None = None
    backdrop_path: ImageUrl | None = None
    logo_path: ImageUrl | None = None
    scrub_preview_path: ImageUrl | None = None

    # Categorization
    genres: list[Genre] = Field(default_factory=list)

    # File variants
    files: list[MediaFile] = Field(default_factory=list)

    # Credits
    cast: list[CastMember] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    writers: list[str] = Field(default_factory=list)

    # Classification
    content_rating: ContentRating | None = None

    # Trailer
    trailer_url: str | None = None

    # Collection / franchise on TMDB (Alien Collection, MCU, ...)
    collection: Collection | None = None

    # Localized metadata: {"pt-BR": {"title": "...", "synopsis": "...", "genres": [...]}}
    localized: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # External IDs for metadata enrichment
    tmdb_id: TmdbId | None = None
    imdb_id: ImdbId | None = None

    # Set true when the movie needs an enrichment review — either an
    # enrichment attempt couldn't resolve a TMDB match (off-year movie,
    # cross-type miss, ambiguous title, …) or an operator flagged the
    # result as wrong (matched the wrong title). Read by the admin
    # "needs review" listing so the operator can relink manually.
    # Cleared on the next successful enrichment.
    needs_enrichment_review: bool = False

    # Skip-credits support (per-file detection; credits run to the end)
    credits: CreditsMarker | None = None
    credits_detection_state: CreditsDetectionState = CreditsDetectionState.NOT_STARTED

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | MovieId | None) -> MovieId | None:
        """Convert string to MovieId if needed."""
        if v is None:
            return None
        return MovieId(v) if isinstance(v, str) else v

    # noinspection PyNestedDecorators
    @field_validator("genres", mode="before")
    @classmethod
    def convert_genres(cls, v: list[Any] | None) -> list[Genre]:
        """Convert string list to Genre list."""
        return [] if v is None else [Genre(g) if isinstance(g, str) else g for g in v]

    # ── localized accessors ────────────────────────────────────────────

    def get_title(self, lang: str = "en") -> str:
        """Get title in the requested language, falling back to default."""
        loc = self.localized.get(lang, {})
        return str(loc.get("title") or self.title.value)

    def get_synopsis(self, lang: str = "en") -> str | None:
        """Get synopsis in the requested language, falling back to default."""
        loc = self.localized.get(lang, {})
        return str(loc["synopsis"]) if loc.get("synopsis") else self.synopsis

    def get_tagline(self, lang: str = "en") -> str | None:
        """Get tagline in the requested language, falling back to default."""
        loc = self.localized.get(lang, {})
        return str(loc["tagline"]) if loc.get("tagline") else self.tagline

    def get_genres(self, lang: str = "en") -> list[str]:
        """Get genres in the requested language, falling back to default."""
        loc = self.localized.get(lang, {})
        loc_genres = loc.get("genres")
        if loc_genres and isinstance(loc_genres, list):
            return [str(g) for g in loc_genres]
        return [g.value for g in self.genres]

    def get_logo_path(self, lang: str = "en") -> str | None:
        """Get title-logo URL for the requested language.

        Falls back to ``self.logo_path`` (the language at enrich time,
        typically en) when the language has no localized override —
        mirroring how ``get_title`` / ``get_synopsis`` behave so the
        UI sees a consistent "best available" graphic per language.
        """
        loc = self.localized.get(lang, {})
        loc_logo = loc.get("logo_path")
        if loc_logo:
            return str(loc_logo)
        return self.logo_path.value if self.logo_path else None

    def get_poster_path(self, lang: str = "en") -> str | None:
        """Get poster URL for the requested language, falling back to default.

        Mirrors ``get_logo_path``: returns the locale's localized poster
        when present, else the global (English base) ``poster_path``.
        """
        loc = self.localized.get(lang, {})
        loc_poster = loc.get("poster_path")
        if loc_poster:
            return str(loc_poster)
        return self.poster_path.value if self.poster_path else None

    def get_backdrop_path(self, lang: str = "en") -> str | None:
        """Get backdrop URL for the requested language, falling back to default."""
        loc = self.localized.get(lang, {})
        loc_backdrop = loc.get("backdrop_path")
        if loc_backdrop:
            return str(loc_backdrop)
        return self.backdrop_path.value if self.backdrop_path else None

    # ── genre helpers ─────────────────────────────────────────────────

    def with_genre(self, genre: Genre | str) -> Self:
        """Return a copy with the genre added.

        Args:
            genre: The genre to add (string or Genre object).

        Returns:
            A new Movie with the genre added, or self if duplicate.
        """
        if isinstance(genre, str):
            genre = Genre(genre)
        if genre in self.genres:
            return self
        return self.with_updates(genres=[*self.genres, genre])

    # ── enrichment review ─────────────────────────────────────────────

    def with_enrichment_review_flagged(self) -> Self:
        """Return a copy flagged for manual enrichment review.

        Used when an operator decides the current metadata is wrong
        (the enrichment matched the wrong title) and wants the movie
        back in the admin review queue. Idempotent — returns ``self``
        when the flag is already set so no spurious ``updated_at`` bump
        happens. The flag is cleared on the next successful enrichment
        (see ``EnrichMovieMetadataUseCase``).

        Returns:
            A new Movie with ``needs_enrichment_review=True``, or
            ``self`` if it was already flagged.
        """
        if self.needs_enrichment_review:
            return self
        return self.with_updates(needs_enrichment_review=True)

    # ── skip-credits ──────────────────────────────────────────────────

    def with_credits_marker(self, marker: CreditsMarker) -> Self:
        """Return a copy with the credits marker set.

        Args:
            marker: The credits marker to attach to this movie.

        Returns:
            A new Movie with the marker applied, or ``self`` if the same
            marker is already in place.

        Raises:
            BusinessRuleViolationException: If ``marker.start_seconds``
                exceeds the movie's duration.
        """
        if marker.start_seconds > self.duration.value:
            raise BusinessRuleViolationException(
                message="Credits start_seconds cannot exceed movie duration",
                rule_code=MediaRuleCodes.CREDITS_EXCEEDS_DURATION,
                tags={
                    "movie_duration": self.duration.value,
                    "credits_start_seconds": marker.start_seconds,
                },
            )
        if self.credits == marker:
            return self
        return self.with_updates(credits=marker)

    def with_credits_cleared(self) -> Self:
        """Return a copy with the credits marker removed, or ``self``."""
        if self.credits is None:
            return self
        return self.with_updates(credits=None)

    def with_credits_detection_state(self, state: CreditsDetectionState) -> Self:
        """Return a copy with the credits-detection state set, or ``self``."""
        if self.credits_detection_state == state:
            return self
        return self.with_updates(credits_detection_state=state)

    # ── factory ───────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        title: str | Title,
        year: int | Year,
        duration: int | Duration,
        file_path: str | FilePath,
        file_size: int,
        resolution: str | Resolution,
        library_id: str,
        **kwargs: Any,
    ) -> Movie:
        """Factory method with automatic ID generation.

        Args:
            title: Movie title.
            year: Release year.
            duration: Duration in seconds.
            file_path: Path to the video file.
            file_size: File size in bytes.
            resolution: Video resolution.
            library_id: External id (``lib_xxx``) of the owning Library.
            **kwargs: Additional optional fields.

        Returns:
            A new Movie instance with generated ID.
        """
        movie_id = MovieId.generate()

        if isinstance(title, str):
            title = Title(title)
        if isinstance(year, int):
            year = Year(year)
        if isinstance(duration, int):
            duration = Duration(duration)
        if isinstance(file_path, str):
            file_path = FilePath(file_path)
        if isinstance(resolution, str):
            resolution = Resolution(resolution)

        file = MediaFile(
            file_path=file_path,
            file_size=file_size,
            resolution=resolution,
            is_primary=True,
        )

        movie = cls(
            id=movie_id,
            library_id=library_id,
            title=title,
            year=year,
            duration=duration,
            files=[file],
            **kwargs,
        )
        movie.add_event(MediaCreatedEvent(media_id=movie_id, media_type=MediaType.MOVIE))
        return movie


__all__ = ["Movie"]
