"""Tests for GetFeaturedMediaUseCase."""

import pytest

from src.modules.media.application.dtos.featured_dtos import (
    FeaturedItemOutput,
    GetFeaturedInput,
)
from src.modules.media.application.use_cases.get_featured_media import (
    GetFeaturedMediaUseCase,
)
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.value_objects import ImageUrl
from tests.modules.media.unit.conftest import (
    FakeProfileLibraryAccessPort,
    make_media_uow_mock,
    make_profile_library_access,
)

_LIBRARY_ID = "lib_test12345678"
_LIBRARY_ID_OTHER = "lib_otherlibrary"
_PROFILE_ID = "prf_test12345678"


def _make_movie(title: str = "Inception", *, library_id: str = _LIBRARY_ID) -> Movie:
    movie = Movie.create(
        library_id=library_id,
        title=title,
        year=2010,
        duration=8880,
        file_path=f"/movies/{title.lower()}.mkv",
        file_size=4_000_000_000,
        resolution="1080p",
    )
    return movie.with_updates(
        backdrop_path=ImageUrl("https://image.tmdb.org/backdrop.jpg"),
    )


def _make_series(title: str = "Breaking Bad", *, library_id: str = _LIBRARY_ID) -> Series:
    series = Series.create(library_id=library_id, title=title, start_year=2008)
    return series.with_updates(
        backdrop_path=ImageUrl("https://image.tmdb.org/series_backdrop.jpg"),
    )


@pytest.mark.unit
class TestGetFeaturedMediaUseCase:
    """Tests for GetFeaturedMediaUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_movies_only(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = [_make_movie("Inception")]
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=10)
        )

        assert len(result) == 1
        assert isinstance(result[0], FeaturedItemOutput)
        assert result[0].type == "movie"
        assert result[0].title == "Inception"
        mocks.series.find_random.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_return_series_only(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_random.return_value = [_make_series("Breaking Bad")]
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="series", limit=10)
        )

        assert len(result) == 1
        assert result[0].type == "series"
        assert result[0].title == "Breaking Bad"
        mocks.movies.find_random.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_return_both_movies_and_series_when_all(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = [_make_movie("Inception")]
        mocks.series.find_random.return_value = [_make_series("Breaking Bad")]
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="all", limit=10)
        )

        assert len(result) == 2
        types = {item.type for item in result}
        assert types == {"movie", "series"}

    @pytest.mark.asyncio
    async def test_should_truncate_to_limit(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = [_make_movie(f"Movie{i}") for i in range(5)]
        mocks.series.find_random.return_value = [_make_series(f"Series{i}") for i in range(5)]
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="all", limit=4)
        )

        assert len(result) == 4

    @pytest.mark.asyncio
    async def test_should_return_empty_when_no_results(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = []
        mocks.series.find_random.return_value = []
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="all", limit=10)
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_should_filter_with_backdrop(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = []
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=5)
        )

        mocks.movies.find_random.assert_called_once_with(
            5, with_backdrop=True, allowed_library_ids=[_LIBRARY_ID]
        )

    @pytest.mark.asyncio
    async def test_should_pass_language_to_movie_outputs(self) -> None:
        movie = _make_movie("Inception")
        movie = movie.with_updates(
            localized={"pt-BR": {"title": "A Origem"}},
        )
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = [movie]
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=1, lang="pt-BR")
        )

        assert result[0].title == "A Origem"

    @pytest.mark.asyncio
    async def test_movie_output_should_include_backdrop_and_genres(self) -> None:
        movie = _make_movie("Inception")
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = [movie]
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=1)
        )

        assert result[0].backdrop_path == "https://image.tmdb.org/backdrop.jpg"
        assert result[0].year == 2010
        assert result[0].duration_formatted is not None

    @pytest.mark.asyncio
    async def test_series_output_should_have_no_duration(self) -> None:
        series = _make_series("Breaking Bad")
        mocks = make_media_uow_mock()
        mocks.series.find_random.return_value = [series]
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="series", limit=1)
        )

        assert result[0].duration_formatted is None
        assert result[0].year == 2008

    @pytest.mark.asyncio
    async def test_should_short_circuit_for_deny_all_profile(self) -> None:
        mocks = make_media_uow_mock()
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: []}),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="all", limit=10)
        )

        assert result == []
        mocks.factory.assert_not_called()
        mocks.movies.find_random.assert_not_called()
        mocks.series.find_random.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_forward_only_allowed_libraries_for_inclusion_path(
        self,
    ) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = [_make_movie("Visible")]
        mocks.series.find_random.return_value = []
        use_case = GetFeaturedMediaUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: [_LIBRARY_ID]}),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="all", limit=5)
        )

        assert [item.title for item in result] == ["Visible"]
        movie_kwargs = mocks.movies.find_random.call_args.kwargs
        series_kwargs = mocks.series.find_random.call_args.kwargs
        assert list(movie_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
        assert list(series_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
        assert _LIBRARY_ID_OTHER not in list(movie_kwargs["allowed_library_ids"])
