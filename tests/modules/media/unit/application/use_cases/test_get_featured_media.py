"""Tests for GetFeaturedMediaUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.modules.media.application.dtos.featured_dtos import (
    FeaturedItemOutput,
    GetFeaturedInput,
)
from src.modules.media.application.use_cases.get_featured_media import (
    GetFeaturedMediaUseCase,
)
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import ImageUrl


def _make_movie(title: str = "Inception") -> Movie:
    movie = Movie.create(
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


def _make_series(title: str = "Breaking Bad") -> Series:
    series = Series.create(title=title, start_year=2008)
    return series.with_updates(
        backdrop_path=ImageUrl("https://image.tmdb.org/series_backdrop.jpg"),
    )


@pytest.mark.unit
class TestGetFeaturedMediaUseCase:
    """Tests for GetFeaturedMediaUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_movies_only(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_random.return_value = [_make_movie("Inception")]
        series_repo = AsyncMock(spec=SeriesRepository)
        use_case = GetFeaturedMediaUseCase(
            movie_repository=movie_repo,
            series_repository=series_repo,
        )

        result = await use_case.execute(GetFeaturedInput(media_type="movie", limit=10))

        assert len(result) == 1
        assert isinstance(result[0], FeaturedItemOutput)
        assert result[0].type == "movie"
        assert result[0].title == "Inception"
        series_repo.find_random.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_return_series_only(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        series_repo.find_random.return_value = [_make_series("Breaking Bad")]
        use_case = GetFeaturedMediaUseCase(
            movie_repository=movie_repo,
            series_repository=series_repo,
        )

        result = await use_case.execute(GetFeaturedInput(media_type="series", limit=10))

        assert len(result) == 1
        assert result[0].type == "series"
        assert result[0].title == "Breaking Bad"
        movie_repo.find_random.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_return_both_movies_and_series_when_all(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_random.return_value = [_make_movie("Inception")]
        series_repo = AsyncMock(spec=SeriesRepository)
        series_repo.find_random.return_value = [_make_series("Breaking Bad")]
        use_case = GetFeaturedMediaUseCase(
            movie_repository=movie_repo,
            series_repository=series_repo,
        )

        result = await use_case.execute(GetFeaturedInput(media_type="all", limit=10))

        assert len(result) == 2
        types = {item.type for item in result}
        assert types == {"movie", "series"}

    @pytest.mark.asyncio
    async def test_should_truncate_to_limit(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_random.return_value = [_make_movie(f"Movie{i}") for i in range(5)]
        series_repo = AsyncMock(spec=SeriesRepository)
        series_repo.find_random.return_value = [_make_series(f"Series{i}") for i in range(5)]
        use_case = GetFeaturedMediaUseCase(
            movie_repository=movie_repo,
            series_repository=series_repo,
        )

        result = await use_case.execute(GetFeaturedInput(media_type="all", limit=4))

        assert len(result) == 4

    @pytest.mark.asyncio
    async def test_should_return_empty_when_no_results(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_random.return_value = []
        series_repo = AsyncMock(spec=SeriesRepository)
        series_repo.find_random.return_value = []
        use_case = GetFeaturedMediaUseCase(
            movie_repository=movie_repo,
            series_repository=series_repo,
        )

        result = await use_case.execute(GetFeaturedInput(media_type="all", limit=10))

        assert result == []

    @pytest.mark.asyncio
    async def test_should_filter_with_backdrop(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_random.return_value = []
        series_repo = AsyncMock(spec=SeriesRepository)
        series_repo.find_random.return_value = []
        use_case = GetFeaturedMediaUseCase(
            movie_repository=movie_repo,
            series_repository=series_repo,
        )

        await use_case.execute(GetFeaturedInput(media_type="movie", limit=5))

        movie_repo.find_random.assert_called_once_with(5, with_backdrop=True)

    @pytest.mark.asyncio
    async def test_should_pass_language_to_movie_outputs(self) -> None:
        movie = _make_movie("Inception")
        movie = movie.with_updates(
            localized={"pt-BR": {"title": "A Origem"}},
        )
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_random.return_value = [movie]
        series_repo = AsyncMock(spec=SeriesRepository)
        use_case = GetFeaturedMediaUseCase(
            movie_repository=movie_repo,
            series_repository=series_repo,
        )

        result = await use_case.execute(GetFeaturedInput(media_type="movie", limit=1, lang="pt-BR"))

        assert result[0].title == "A Origem"

    @pytest.mark.asyncio
    async def test_movie_output_should_include_backdrop_and_genres(self) -> None:
        movie = _make_movie("Inception")
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_random.return_value = [movie]
        series_repo = AsyncMock(spec=SeriesRepository)
        use_case = GetFeaturedMediaUseCase(
            movie_repository=movie_repo,
            series_repository=series_repo,
        )

        result = await use_case.execute(GetFeaturedInput(media_type="movie", limit=1))

        assert result[0].backdrop_path == "https://image.tmdb.org/backdrop.jpg"
        assert result[0].year == 2010
        assert result[0].duration_formatted is not None

    @pytest.mark.asyncio
    async def test_series_output_should_have_no_duration(self) -> None:
        series = _make_series("Breaking Bad")
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        series_repo.find_random.return_value = [series]
        use_case = GetFeaturedMediaUseCase(
            movie_repository=movie_repo,
            series_repository=series_repo,
        )

        result = await use_case.execute(GetFeaturedInput(media_type="series", limit=1))

        assert result[0].duration_formatted is None
        assert result[0].year == 2008
