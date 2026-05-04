"""Tests for ``GetRelatedMoviesUseCase``."""

from unittest.mock import AsyncMock

import pytest

from src.modules.media.application.ports import MetadataProvider
from src.modules.media.application.use_cases.get_related_movies import (
    GetRelatedMoviesInput,
    GetRelatedMoviesUseCase,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects import MovieId, TmdbId
from tests.modules.media.unit.conftest import (
    FakeProfileLibraryAccessPort,
    make_media_uow_mock,
)

_LIBRARY_ID = "lib_test12345678"
_PROFILE_ID = "prf_test12345678"


def _movie(*, title: str, tmdb_id: int | None) -> Movie:
    movie = Movie.create(
        library_id=_LIBRARY_ID,
        title=title,
        year=2010,
        duration=8880,
        file_path=f"/movies/{title.lower()}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
    )
    return movie.with_updates(tmdb_id=TmdbId(tmdb_id)) if tmdb_id is not None else movie


def _make_use_case(mocks, provider, *, allowed: list[str] | None = None) -> GetRelatedMoviesUseCase:
    if allowed is None:
        allowed = [_LIBRARY_ID]
    return GetRelatedMoviesUseCase(
        mocks.factory,
        provider,
        FakeProfileLibraryAccessPort({_PROFILE_ID: allowed}),
    )


class TestGetRelatedMoviesUseCase:
    @pytest.mark.asyncio
    async def test_returns_empty_when_source_movie_missing(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = None
        provider = AsyncMock(spec=MetadataProvider)

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedMoviesInput(profile_id=_PROFILE_ID, movie_id=str(MovieId.generate())),
        )

        assert result == []
        provider.get_movie_recommendations.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_when_source_has_no_tmdb_id(self) -> None:
        # Movie was added manually (no enrich) — no way to look up
        # recommendations. Bail before hitting the provider.
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = _movie(title="Manual", tmdb_id=None)
        provider = AsyncMock(spec=MetadataProvider)

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedMoviesInput(profile_id=_PROFILE_ID, movie_id=str(MovieId.generate())),
        )

        assert result == []
        provider.get_movie_recommendations.assert_not_called()

    @pytest.mark.asyncio
    async def test_filters_to_local_catalog_preserving_tmdb_order(self) -> None:
        # TMDB returns 4 ids in relevance order. Only ids 1422 and 27205
        # exist locally; the response must be ordered [1422, 27205] —
        # TMDB's relevance ranking, NOT the dict's insertion order.
        mocks = make_media_uow_mock()
        source = _movie(title="The Dark Knight", tmdb_id=155)
        mocks.movies.find_by_id.return_value = source
        mocks.movies.find_by_tmdb_ids.return_value = {
            27205: _movie(title="Inception", tmdb_id=27205),
            1422: _movie(title="The Departed", tmdb_id=1422),
        }
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_movie_recommendations.return_value = [
            1422,
            999999,
            27205,
            888888,
        ]

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedMoviesInput(
                profile_id=_PROFILE_ID,
                movie_id=str(MovieId.generate()),
                limit=10,
            ),
        )

        assert [m.title for m in result] == ["The Departed", "Inception"]
        # Both repo calls must carry the ACL.
        find_by_id_kwargs = mocks.movies.find_by_id.await_args.kwargs
        find_by_tmdb_ids_kwargs = mocks.movies.find_by_tmdb_ids.await_args.kwargs
        assert list(find_by_id_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
        assert list(find_by_tmdb_ids_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]

    @pytest.mark.asyncio
    async def test_truncates_to_limit(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = _movie(title="Source", tmdb_id=1)
        mocks.movies.find_by_tmdb_ids.return_value = {
            i: _movie(title=f"M{i}", tmdb_id=i) for i in (10, 11, 12, 13, 14)
        }
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_movie_recommendations.return_value = [10, 11, 12, 13, 14]

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedMoviesInput(
                profile_id=_PROFILE_ID,
                movie_id=str(MovieId.generate()),
                limit=3,
            ),
        )

        assert len(result) == 3
        assert [m.title for m in result] == ["M10", "M11", "M12"]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_local_overlap(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = _movie(title="Source", tmdb_id=1)
        mocks.movies.find_by_tmdb_ids.return_value = {}
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_movie_recommendations.return_value = [99, 100, 101]

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedMoviesInput(profile_id=_PROFILE_ID, movie_id=str(MovieId.generate())),
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_deny_all_profile(self) -> None:
        # Deny-all profile must short-circuit before hitting the
        # provider — no leak of recommendations to a profile that
        # cannot see anything in the catalog.
        mocks = make_media_uow_mock()
        provider = AsyncMock(spec=MetadataProvider)

        use_case = _make_use_case(mocks, provider, allowed=[])
        result = await use_case.execute(
            GetRelatedMoviesInput(profile_id=_PROFILE_ID, movie_id=str(MovieId.generate())),
        )

        assert result == []
        mocks.factory.assert_not_called()
        provider.get_movie_recommendations.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_allowed_library_ids_to_both_repo_calls(self) -> None:
        mocks = make_media_uow_mock()
        # Make sure we hit both find_by_id and find_by_tmdb_ids.
        mocks.movies.find_by_id.return_value = _movie(title="Source", tmdb_id=1)
        mocks.movies.find_by_tmdb_ids.return_value = {10: _movie(title="Visible", tmdb_id=10)}
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_movie_recommendations.return_value = [10]

        use_case = GetRelatedMoviesUseCase(
            mocks.factory,
            provider,
            FakeProfileLibraryAccessPort({_PROFILE_ID: [_LIBRARY_ID]}),
        )
        await use_case.execute(
            GetRelatedMoviesInput(profile_id=_PROFILE_ID, movie_id=str(MovieId.generate()))
        )

        find_by_id_kwargs = mocks.movies.find_by_id.await_args.kwargs
        find_by_tmdb_ids_kwargs = mocks.movies.find_by_tmdb_ids.await_args.kwargs
        assert list(find_by_id_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
        assert list(find_by_tmdb_ids_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
