"""ListMoviesByActorUseCase - paginated listing of movies for one actor."""

from dataclasses import dataclass

from src.building_blocks.application.pagination import DEFAULT_PAGE_SIZE
from src.modules.media.application.dtos.movie_dtos import MovieSummaryOutput
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._movie_summary_helpers import to_movie_summary


@dataclass(frozen=True)
class ListMoviesByActorInput:
    """Input for ``ListMoviesByActorUseCase``.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case
            consults ``ProfileLibraryAccessPort`` and restricts the
            page to libraries the profile may see; a deny-all profile
            yields an empty page without opening a UoW.
        actor_name: Exact display name of the cast member. Match is
            by literal equality against the stored ``cast[].name``
            values; collisions between two real people who share a
            name aren't disambiguated (no TMDB person id is persisted
            yet — see CLAUDE.md roadmap).
        cursor: Opaque title cursor from the previous page, or
            ``None`` for the first page.
        limit: Page size. Routes clamp this to ``[1, MAX_PAGE_SIZE]``
            before constructing the input.
        lang: Language code for localized titles / synopses / genres
            on the returned summaries.
    """

    profile_id: str
    actor_name: str
    cursor: str | None = None
    limit: int = DEFAULT_PAGE_SIZE
    lang: str = "en"


@dataclass(frozen=True)
class ListMoviesByActorOutput:
    """Output for ``ListMoviesByActorUseCase``.

    Attributes:
        movies: Movies that have ``actor_name`` in their cast,
            sorted alphabetically by title.
        next_cursor: Opaque token to pass back as ``cursor`` on the
            next request, or ``None`` when there are no more pages.
        has_more: Convenience flag — equivalent to
            ``next_cursor is not None`` but explicit so clients don't
            have to infer it.
    """

    movies: list[MovieSummaryOutput]
    next_cursor: str | None
    has_more: bool


class ListMoviesByActorUseCase:
    """List movies whose cast contains the given actor, paginated.

    Single-stream listing — series cast isn't part of the domain yet
    (deferred to a follow-up that extends ``Series`` with cast), so
    only the movies repo is queried. When series cast lands, this
    use case can be promoted to a dual-stream merge mirroring
    ``ListByGenreUseCase`` without breaking the API contract.
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        profile_library_access: ProfileLibraryAccessPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._profile_library_access = profile_library_access

    async def execute(self, input_dto: ListMoviesByActorInput) -> ListMoviesByActorOutput:
        """Execute the use case.

        Args:
            input_dto: ``profile_id``, ``actor_name`` (exact display
                name), ``cursor``, ``limit``, ``lang``.

        Returns:
            ``ListMoviesByActorOutput`` carrying the page of summaries
            plus the next cursor. A deny-all profile yields an empty
            page without opening a UoW.
        """
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
            return ListMoviesByActorOutput(movies=[], next_cursor=None, has_more=False)

        async with self._uow_factory() as uow:
            page = await uow.movies.list_paginated_by_cast_member(
                actor_name=input_dto.actor_name,
                cursor=input_dto.cursor,
                limit=input_dto.limit,
                allowed_library_ids=allowed,
            )

        return ListMoviesByActorOutput(
            movies=[to_movie_summary(movie, input_dto.lang) for movie in page.items],
            next_cursor=page.pagination.next_cursor,
            has_more=page.pagination.has_more,
        )


__all__ = [
    "ListMoviesByActorInput",
    "ListMoviesByActorOutput",
    "ListMoviesByActorUseCase",
]
