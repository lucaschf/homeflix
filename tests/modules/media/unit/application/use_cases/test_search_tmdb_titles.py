"""Tests for SearchTmdbTitlesUseCase routing."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.application.dtos.tmdb_lookup_dtos import (
    SearchTmdbTitlesInput,
)
from src.modules.media.application.use_cases.search_tmdb_titles import (
    SearchTmdbTitlesUseCase,
)
from src.modules.metadata.application.ports.metadata_provider_port import SearchCandidate


def _empty_uow_factory() -> MagicMock:
    """A UoW factory whose catalog repos report nothing already hosted."""
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.movies.find_by_tmdb_ids.return_value = {}
    uow.series.find_by_tmdb_ids.return_value = {}
    return MagicMock(return_value=uow)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_marks_candidate_already_in_catalog() -> None:
    """A candidate whose tmdb_id is hosted locally is flagged in_catalog."""
    provider = AsyncMock()
    provider.get_movie_summary_by_id.return_value = _movie_candidate(tmdb_id=603)
    provider.get_series_summary_by_id.return_value = None

    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.movies.find_by_tmdb_ids.return_value = {603: object()}  # already hosted
    uow.series.find_by_tmdb_ids.return_value = {}
    use_case = SearchTmdbTitlesUseCase(
        metadata_provider=provider,
        uow_factory=MagicMock(return_value=uow),
    )

    out = await use_case.execute(SearchTmdbTitlesInput(query="603", limit=5))

    assert [c.in_catalog for c in out.candidates] == [True]


def _movie_candidate(tmdb_id: int = 603, title: str = "The Matrix") -> SearchCandidate:
    return SearchCandidate(
        tmdb_id=tmdb_id,
        media_type="movie",
        title=title,
        year=1999,
        overview="A computer hacker learns…",
        poster_url="https://image.tmdb.org/p.jpg",
    )


def _series_candidate(tmdb_id: int = 1399, title: str = "Game of Thrones") -> SearchCandidate:
    return SearchCandidate(
        tmdb_id=tmdb_id,
        media_type="tv",
        title=title,
        year=2011,
        overview="Seven noble families fight…",
        poster_url="https://image.tmdb.org/g.jpg",
    )


class TestTmdbUrlBranch:
    @pytest.mark.asyncio
    async def test_tmdb_movie_url_calls_movie_summary_only(self) -> None:
        provider = AsyncMock()
        provider.get_movie_summary_by_id.return_value = _movie_candidate()

        use_case = SearchTmdbTitlesUseCase(
            metadata_provider=provider, uow_factory=_empty_uow_factory()
        )
        out = await use_case.execute(
            SearchTmdbTitlesInput(query="https://www.themoviedb.org/movie/603"),
        )

        assert out.kind == "tmdb_id"
        assert len(out.candidates) == 1
        assert out.candidates[0].tmdb_id == 603
        provider.get_movie_summary_by_id.assert_awaited_once_with(603)
        provider.get_series_summary_by_id.assert_not_called()
        provider.find_movie_candidates.assert_not_called()

    @pytest.mark.asyncio
    async def test_tmdb_tv_url_calls_series_summary_only(self) -> None:
        provider = AsyncMock()
        provider.get_series_summary_by_id.return_value = _series_candidate()

        use_case = SearchTmdbTitlesUseCase(
            metadata_provider=provider, uow_factory=_empty_uow_factory()
        )
        out = await use_case.execute(
            SearchTmdbTitlesInput(query="https://www.themoviedb.org/tv/1399"),
        )

        assert out.kind == "tmdb_id"
        assert len(out.candidates) == 1
        assert out.candidates[0].media_type == "tv"
        provider.get_series_summary_by_id.assert_awaited_once_with(1399)
        provider.get_movie_summary_by_id.assert_not_called()


class TestImdbBranch:
    @pytest.mark.asyncio
    async def test_imdb_url_calls_find(self) -> None:
        provider = AsyncMock()
        provider.find_by_imdb_id.return_value = [_movie_candidate()]

        use_case = SearchTmdbTitlesUseCase(
            metadata_provider=provider, uow_factory=_empty_uow_factory()
        )
        out = await use_case.execute(
            SearchTmdbTitlesInput(query="https://www.imdb.com/title/tt0133093/"),
        )

        assert out.kind == "imdb_id"
        assert out.query == "tt0133093"
        provider.find_by_imdb_id.assert_awaited_once_with("tt0133093")

    @pytest.mark.asyncio
    async def test_bare_imdb_id_calls_find(self) -> None:
        provider = AsyncMock()
        provider.find_by_imdb_id.return_value = [
            _movie_candidate(),
            _series_candidate(),
        ]

        use_case = SearchTmdbTitlesUseCase(
            metadata_provider=provider, uow_factory=_empty_uow_factory()
        )
        out = await use_case.execute(SearchTmdbTitlesInput(query="tt0133093"))

        assert out.kind == "imdb_id"
        assert [c.tmdb_id for c in out.candidates] == [603, 1399]


class TestBareNumericBranch:
    @pytest.mark.asyncio
    async def test_bare_numeric_tries_both_kinds_in_parallel(self) -> None:
        provider = AsyncMock()
        provider.get_movie_summary_by_id.return_value = _movie_candidate(603)
        provider.get_series_summary_by_id.return_value = _series_candidate(603)

        use_case = SearchTmdbTitlesUseCase(
            metadata_provider=provider, uow_factory=_empty_uow_factory()
        )
        out = await use_case.execute(SearchTmdbTitlesInput(query="603"))

        provider.get_movie_summary_by_id.assert_awaited_once_with(603)
        provider.get_series_summary_by_id.assert_awaited_once_with(603)
        # Movies first, then series.
        assert [c.media_type for c in out.candidates] == ["movie", "tv"]

    @pytest.mark.asyncio
    async def test_bare_numeric_drops_kind_with_no_match(self) -> None:
        provider = AsyncMock()
        provider.get_movie_summary_by_id.return_value = _movie_candidate(603)
        provider.get_series_summary_by_id.return_value = None

        use_case = SearchTmdbTitlesUseCase(
            metadata_provider=provider, uow_factory=_empty_uow_factory()
        )
        out = await use_case.execute(SearchTmdbTitlesInput(query="603"))

        assert len(out.candidates) == 1
        assert out.candidates[0].media_type == "movie"


class TestTextBranch:
    @pytest.mark.asyncio
    async def test_plain_text_calls_both_searches_with_limit(self) -> None:
        provider = AsyncMock()
        provider.find_movie_candidates.return_value = [_movie_candidate()]
        provider.find_series_candidates.return_value = [_series_candidate()]

        use_case = SearchTmdbTitlesUseCase(
            metadata_provider=provider, uow_factory=_empty_uow_factory()
        )
        out = await use_case.execute(
            SearchTmdbTitlesInput(query="  matrix  ", limit=3),
        )

        assert out.kind == "text"
        assert out.query == "matrix"
        provider.find_movie_candidates.assert_awaited_once_with("matrix", year=None, limit=3)
        provider.find_series_candidates.assert_awaited_once_with("matrix", year=None, limit=3)
        # Movies first.
        assert [c.media_type for c in out.candidates] == ["movie", "tv"]

    @pytest.mark.asyncio
    async def test_limit_is_clamped_to_provider_friendly_range(self) -> None:
        provider = AsyncMock()
        provider.find_movie_candidates.return_value = []
        provider.find_series_candidates.return_value = []

        use_case = SearchTmdbTitlesUseCase(
            metadata_provider=provider, uow_factory=_empty_uow_factory()
        )
        await use_case.execute(SearchTmdbTitlesInput(query="x", limit=1000))

        # Use case caps at 20 internally even if a misbehaving caller
        # passes through the route validation somehow.
        provider.find_movie_candidates.assert_awaited_once_with("x", year=None, limit=20)


class TestEmptyInput:
    @pytest.mark.asyncio
    async def test_whitespace_only_returns_empty_without_calling_provider(self) -> None:
        provider = AsyncMock()

        use_case = SearchTmdbTitlesUseCase(
            metadata_provider=provider, uow_factory=_empty_uow_factory()
        )
        out = await use_case.execute(SearchTmdbTitlesInput(query="   "))

        assert out.candidates == []
        assert out.kind == "text"
        provider.find_movie_candidates.assert_not_called()
        provider.find_series_candidates.assert_not_called()
        provider.find_by_imdb_id.assert_not_called()
