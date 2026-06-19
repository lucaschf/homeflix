"""GetMovieByIdUseCase - Retrieve a single movie by ID."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.movie_dtos import (
    CastMemberOutput,
    CollectionOutput,
    GetMovieByIdInput,
    MovieOutput,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._credits_media_helpers import (
    to_credits_marker_output,
)
from src.modules.media.application.use_cases._media_file_helpers import (
    to_media_file_output,
)
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.value_objects import MovieId


class GetMovieByIdUseCase:
    """Retrieve a single movie by its external ID.

    This use case fetches a movie from the repository and returns
    it in a format suitable for API consumption.

    Per ADR-010, the lookup is restricted to the caller's
    ``Profile.allowed_library_ids`` via ``ProfileLibraryAccessPort``. A
    movie that exists outside the ACL surfaces as
    ``ResourceNotFoundException`` (HTTP 404), preventing the catalog
    ACL from being bypassed by id-poking. A deny-all profile
    short-circuits to a 404 without opening the UoW.

    Example:
        >>> use_case = GetMovieByIdUseCase(uow_factory, profile_library_access)
        >>> result = await use_case.execute(
        ...     GetMovieByIdInput(profile_id="prf_abc", movie_id="mov_abc123")
        ... )
        >>> result.title
        'Inception'
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        profile_library_access: ProfileLibraryAccessPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
            profile_library_access: Port that resolves the caller's
                allowed library_ids.
        """
        self._uow_factory = uow_factory
        self._profile_library_access = profile_library_access

    async def execute(self, input_dto: GetMovieByIdInput) -> MovieOutput:
        """Execute the use case.

        Args:
            input_dto: Contains the profile_id and movie_id to fetch.

        Returns:
            MovieOutput with all movie details.

        Raises:
            ResourceNotFoundException: If the movie does not exist or
                lives in a library outside the caller's ACL.
        """
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
            raise ResourceNotFoundException.for_resource("Movie", input_dto.movie_id)

        movie_id = MovieId(input_dto.movie_id)
        async with self._uow_factory() as uow:
            movie = await uow.movies.find_by_id(movie_id, allowed_library_ids=allowed)

        if movie is None:
            raise ResourceNotFoundException.for_resource("Movie", input_dto.movie_id)

        return self._to_output(movie, input_dto.lang)

    @staticmethod
    def _to_output(movie: Movie, lang: str = "en") -> MovieOutput:
        """Convert Movie entity to output DTO.

        Args:
            movie: The Movie entity to convert.
            lang: Language code for localized fields.

        Returns:
            MovieOutput with all fields serialized.
        """
        primary = movie.primary_file
        return MovieOutput(
            id=str(movie.id),
            title=movie.get_title(lang),
            original_title=movie.original_title.value if movie.original_title else None,
            year=movie.year.value,
            duration_seconds=movie.duration.value,
            duration_formatted=movie.duration.format_hms(),
            synopsis=movie.get_synopsis(lang),
            tagline=movie.get_tagline(lang),
            poster_path=movie.poster_path.value if movie.poster_path else None,
            backdrop_path=movie.backdrop_path.value if movie.backdrop_path else None,
            logo_path=movie.get_logo_path(lang),
            scrub_preview_path=movie.scrub_preview_path.value if movie.scrub_preview_path else None,
            genres=movie.get_genres(lang),
            cast=[
                CastMemberOutput(
                    name=m.name,
                    profile_path=m.profile_path,
                    role=m.role,
                    tmdb_id=m.tmdb_id,
                )
                for m in movie.cast
            ],
            directors=movie.directors,
            writers=movie.writers,
            content_rating=movie.content_rating.value if movie.content_rating else None,
            trailer_url=movie.trailer_url,
            collection=CollectionOutput(
                tmdb_id=movie.collection.tmdb_id,
                name=movie.collection.name,
                parts_count=movie.collection.parts_count,
            )
            if movie.collection
            else None,
            file_path=primary.file_path.value if primary else None,
            file_size=primary.file_size if primary else None,
            resolution=primary.resolution.value if primary else None,
            files=[to_media_file_output(f) for f in movie.files],
            tmdb_id=movie.tmdb_id.value if movie.tmdb_id else None,
            imdb_id=movie.imdb_id.value if movie.imdb_id else None,
            needs_enrichment_review=movie.needs_enrichment_review,
            created_at=movie.created_at.isoformat(),
            updated_at=movie.updated_at.isoformat(),
            credits=to_credits_marker_output(movie.credits),
        )


__all__ = ["GetMovieByIdUseCase"]
