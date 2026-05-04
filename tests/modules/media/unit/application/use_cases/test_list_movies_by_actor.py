"""Tests for ListMoviesByActorUseCase."""

import pytest

from src.building_blocks.application.pagination import PaginatedResult, Pagination
from src.modules.media.application.use_cases.list_movies_by_actor import (
    ListMoviesByActorInput,
    ListMoviesByActorOutput,
    ListMoviesByActorUseCase,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects.cast_member import CastMember
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_movie(
    title: str = "Test Movie",
    year: int = 2020,
    cast: list[CastMember] | None = None,
) -> Movie:
    movie = Movie.create(
        library_id=_LIBRARY_ID,
        title=title,
        year=year,
        duration=7200,
        file_path=f"/movies/{title.lower().replace(' ', '_')}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
    )
    if cast is not None:
        movie = movie.with_updates(cast=cast)
    return movie


def _page(
    movies: list[Movie],
    *,
    next_cursor: str | None = None,
    has_more: bool = False,
) -> PaginatedResult[Movie]:
    return PaginatedResult(
        items=movies,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
        total_count=None,
    )


class TestListMoviesByActorUseCase:
    """Tests for ListMoviesByActorUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_movies_for_actor(self) -> None:
        mocks = make_media_uow_mock()
        cast = [CastMember(name="Sigourney Weaver")]
        mocks.movies.list_paginated_by_cast_member.return_value = _page(
            [
                _make_movie("Alien", 1979, cast=cast),
                _make_movie("Aliens", 1986, cast=cast),
            ]
        )
        use_case = ListMoviesByActorUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListMoviesByActorInput(actor_name="Sigourney Weaver"))

        assert isinstance(result, ListMoviesByActorOutput)
        assert [m.title for m in result.movies] == ["Alien", "Aliens"]
        mocks.movies.list_paginated_by_cast_member.assert_awaited_once_with(
            actor_name="Sigourney Weaver",
            cursor=None,
            limit=20,
        )

    @pytest.mark.asyncio
    async def test_should_pass_cursor_and_limit_to_repository(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_cast_member.return_value = _page([])
        use_case = ListMoviesByActorUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            ListMoviesByActorInput(
                actor_name="Sigourney Weaver",
                cursor="abc123",
                limit=15,
            )
        )

        mocks.movies.list_paginated_by_cast_member.assert_awaited_once_with(
            actor_name="Sigourney Weaver",
            cursor="abc123",
            limit=15,
        )

    @pytest.mark.asyncio
    async def test_should_propagate_pagination_metadata(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_cast_member.return_value = _page(
            [_make_movie("Alien", cast=[CastMember(name="Sigourney Weaver")])],
            next_cursor="next-token",
            has_more=True,
        )
        use_case = ListMoviesByActorUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListMoviesByActorInput(actor_name="Sigourney Weaver"))

        assert result.next_cursor == "next-token"
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_should_return_empty_page_when_no_matches(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_cast_member.return_value = _page([])
        use_case = ListMoviesByActorUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListMoviesByActorInput(actor_name="Nobody Famous"))

        assert result.movies == []
        assert result.has_more is False
        assert result.next_cursor is None
