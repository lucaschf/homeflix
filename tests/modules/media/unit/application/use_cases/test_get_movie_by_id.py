"""Tests for GetMovieByIdUseCase."""


import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import GetMovieByIdInput, MovieOutput
from src.modules.media.application.errors import (
    ContentRestrictedByMaturityError,
    ContentRestrictedUnratedError,
)
from src.modules.media.application.use_cases import GetMovieByIdUseCase
from src.modules.media.domain.entities import Movie
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import (
    AgeRating,
    Certification,
    ContentRating,
    LibraryId,
    RatingSystem,
)
from tests.modules.media.unit.conftest import (
    FakeProfileViewingPolicyPort,
    FixedViewingPolicyPort,
    make_media_uow_mock,
    make_profile_viewing_policy,
)

_LIBRARY_ID = "lib_test12345678"
_PROFILE_ID = "prf_test12345678"


class TestGetMovieByIdUseCase:
    """Tests for GetMovieByIdUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_movie_when_found(self):
        mocks = make_media_uow_mock()
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        mocks.movies.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(
            GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
        )

        assert isinstance(result, MovieOutput)
        assert result.title == "Inception"
        assert result.year == 2010
        assert result.duration_seconds == 8880
        assert result.resolution == "1080p"

    @pytest.mark.asyncio
    async def test_should_return_formatted_duration(self):
        mocks = make_media_uow_mock()
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        mocks.movies.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(
            GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
        )

        assert result.duration_formatted == "02:00:00"

    @pytest.mark.asyncio
    async def test_should_return_genres_as_strings(self):
        mocks = make_media_uow_mock()
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        movie = movie.with_genre("Action")
        movie = movie.with_genre("Sci-Fi")
        mocks.movies.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(
            GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
        )

        assert result.genres == ["Action", "Sci-Fi"]

    @pytest.mark.asyncio
    async def test_should_handle_optional_fields_as_none(self):
        mocks = make_media_uow_mock()
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        mocks.movies.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(
            GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
        )

        assert result.original_title is None
        assert result.synopsis is None
        assert result.poster_path is None
        assert result.backdrop_path is None
        assert result.tmdb_id is None
        assert result.imdb_id is None

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_movie_missing(self):
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = None
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id="mov_nonexistent1")
            )

        assert exc_info.value.resource_type == "Movie"
        assert exc_info.value.resource_id == "mov_nonexistent1"

    @pytest.mark.asyncio
    async def test_should_call_repository_with_movie_id_and_allowed_libraries(self):
        mocks = make_media_uow_mock()
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        mocks.movies.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        await use_case.execute(GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id)))

        mocks.movies.find_by_id.assert_awaited_once()
        call_args = mocks.movies.find_by_id.await_args
        assert str(call_args.args[0]) == str(movie.id)
        assert call_args.kwargs["policy"] == ViewingPolicy.unrestricted([_LIBRARY_ID])

    @pytest.mark.asyncio
    async def test_should_raise_404_for_deny_all_profile(self):
        # Deny-all profile must surface as 404 (matching the behavior
        # for a movie that lives outside the ACL — id-poking should
        # not leak the row's existence). Load-bearing security
        # assertion.
        mocks = make_media_uow_mock()
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=FakeProfileViewingPolicyPort({_PROFILE_ID: []}),
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id="mov_anything12345")
            )
        mocks.factory.assert_not_called()
        mocks.movies.find_by_id.assert_not_awaited()


_OTHER_LIBRARY_ID = "lib_other1234567"
_TITLE = "Restricted Title"


def _certification(label: str, age: int | None) -> Certification:
    return Certification(
        system=RatingSystem.BR_DEJUS if age is not None else RatingSystem.UNKNOWN,
        label=ContentRating(label),
        minimum_age=AgeRating(age) if age is not None else None,
    )


def _rated_movie(certification: Certification | None, *, library_id: str = _LIBRARY_ID) -> Movie:
    return Movie.create(
        library_id=library_id,
        title=_TITLE,
        year=2020,
        duration=7200,
        file_path="/movies/restricted.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
        certification=certification,
    )


def _serve_as_repository(mocks, movie: Movie) -> None:
    """Make ``find_by_id`` answer the way the SQL projection of ``policy`` would.

    The repository filters by the full ``ViewingPolicy`` it is handed
    (held to ``permits()`` by ``test_visibility_projection.py``). Emulating
    that, instead of returning the movie unconditionally, is what makes
    these tests notice a use case that passes the full policy — the
    over-age title would come back ``None`` and surface as a 404.
    """

    async def _find_by_id(movie_id, *, policy=None):
        if str(movie_id) != str(movie.id):
            return None
        if policy is not None and not policy.permits(
            library_id=LibraryId(movie.library_id), minimum_age=movie.minimum_age
        ):
            return None
        return movie

    mocks.movies.find_by_id.side_effect = _find_by_id


def _limited(limit: int, *, libraries: list[str] | None = None) -> FixedViewingPolicyPort:
    return FixedViewingPolicyPort(
        ViewingPolicy(
            allowed_library_ids=[_LIBRARY_ID] if libraries is None else libraries,
            maturity_limit=AgeRating(limit),
        )
    )


class TestGetMovieByIdMaturityGate:
    """ADR-035 §11: 404 on the library axis, 403 on the maturity axis."""

    async def test_should_raise_maturity_403_without_the_title_when_above_limit(self):
        mocks = make_media_uow_mock()
        movie = _rated_movie(_certification("16", 16))
        _serve_as_repository(mocks, movie)
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory, profile_viewing_policy=_limited(12)
        )

        with pytest.raises(ContentRestrictedByMaturityError) as exc_info:
            await use_case.execute(
                GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
            )

        exc = exc_info.value
        assert exc.code == "CONTENT_RESTRICTED_BY_MATURITY"
        body = exc.to_dict()
        assert body["details"] == [
            {
                "code": "CONTENT_RESTRICTED_BY_MATURITY",
                "message": "Requires age 16; profile limit is 12",
                "metadata": {"required_age": 16, "profile_limit": 12},
            }
        ]
        assert _TITLE not in str(body)
        assert str(movie.id) not in str(body)

    @pytest.mark.parametrize(
        "certification",
        [None, _certification("NR", None)],
        ids=["no-certification", "undetermined-label"],
    )
    async def test_should_raise_unrated_403_when_unrated_under_a_limit_below_adult(
        self, certification
    ):
        mocks = make_media_uow_mock()
        movie = _rated_movie(certification)
        _serve_as_repository(mocks, movie)
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory, profile_viewing_policy=_limited(12)
        )

        with pytest.raises(ContentRestrictedUnratedError) as exc_info:
            await use_case.execute(
                GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
            )

        body = exc_info.value.to_dict()
        assert body["code"] == "CONTENT_RESTRICTED_UNRATED"
        assert body["details"][0]["metadata"] == {"profile_limit": 12}
        assert _TITLE not in str(body)

    async def test_should_return_unrated_movie_under_an_adult_limit(self):
        mocks = make_media_uow_mock()
        movie = _rated_movie(None)
        _serve_as_repository(mocks, movie)
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory, profile_viewing_policy=_limited(18)
        )

        result = await use_case.execute(
            GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
        )

        assert result.title == _TITLE

    async def test_should_return_movie_within_the_limit(self):
        mocks = make_media_uow_mock()
        movie = _rated_movie(_certification("12", 12))
        _serve_as_repository(mocks, movie)
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory, profile_viewing_policy=_limited(12)
        )

        result = await use_case.execute(
            GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
        )

        assert result.title == _TITLE
        assert result.content_rating == "12"

    async def test_should_raise_404_not_403_when_outside_libraries_and_above_limit(self):
        # The library axis takes precedence and hides existence: a
        # profile must not learn that a title in a library it cannot
        # reach is also rated above its limit.
        mocks = make_media_uow_mock()
        movie = _rated_movie(_certification("18", 18), library_id=_OTHER_LIBRARY_ID)
        _serve_as_repository(mocks, movie)
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory, profile_viewing_policy=_limited(12)
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
            )

        assert type(exc_info.value) is ResourceNotFoundException

    async def test_should_raise_404_for_deny_all_profile_with_a_limit(self):
        mocks = make_media_uow_mock()
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory, profile_viewing_policy=_limited(12, libraries=[])
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id="mov_anything12345")
            )

        assert type(exc_info.value) is ResourceNotFoundException
        mocks.factory.assert_not_called()
