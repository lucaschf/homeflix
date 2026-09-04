"""Tests for GetFeaturedMediaUseCase."""

from datetime import UTC, datetime

import pytest

from src.modules.media.application.dtos.featured_dtos import (
    FeaturedItemOutput,
    GetFeaturedInput,
)
from src.modules.media.application.ports.watch_history_port import WatchedTitle
from src.modules.media.application.use_cases.get_featured_media import (
    GetFeaturedMediaUseCase,
    rank_genres,
)
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.value_objects import Genre, ImageUrl
from tests.modules.media.unit.conftest import (
    FakeProfileLibraryAccessPort,
    FakeWatchHistoryPort,
    make_media_uow_mock,
    make_profile_library_access,
    make_watch_history,
)

_LIBRARY_ID = "lib_test12345678"
_LIBRARY_ID_OTHER = "lib_otherlibrary"
_PROFILE_ID = "prf_test12345678"
_NOW = datetime(2026, 9, 4, tzinfo=UTC)


def _make_movie(
    title: str = "Inception",
    *,
    library_id: str = _LIBRARY_ID,
    genres: list[str] | None = None,
) -> Movie:
    movie = Movie.create(
        library_id=library_id,
        title=title,
        year=2010,
        duration=8880,
        file_path=f"/movies/{title.lower().replace(' ', '_')}.mkv",
        file_size=4_000_000_000,
        resolution="1080p",
    )
    return movie.with_updates(
        backdrop_path=ImageUrl("https://image.tmdb.org/backdrop.jpg"),
        genres=[Genre(g) for g in (genres or [])],
    )


def _make_series(
    title: str = "Breaking Bad",
    *,
    library_id: str = _LIBRARY_ID,
    genres: list[str] | None = None,
) -> Series:
    series = Series.create(library_id=library_id, title=title, start_year=2008)
    return series.with_updates(
        backdrop_path=ImageUrl("https://image.tmdb.org/series_backdrop.jpg"),
        genres=[Genre(g) for g in (genres or [])],
    )


def _watched(media_id: str, media_type: str, status: str = "completed") -> WatchedTitle:
    return WatchedTitle(
        media_id=media_id, media_type=media_type, status=status, last_watched_at=_NOW
    )


def _use_case(
    mocks,
    *,
    watch_history: FakeWatchHistoryPort | None = None,
    profile_library_access: FakeProfileLibraryAccessPort | None = None,
) -> GetFeaturedMediaUseCase:
    return GetFeaturedMediaUseCase(
        uow_factory=mocks.factory,
        profile_library_access=profile_library_access or make_profile_library_access(),
        watch_history=watch_history or make_watch_history(),
    )


@pytest.mark.unit
class TestGetFeaturedMediaUseCase:
    """Tests for GetFeaturedMediaUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_movies_only(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = [_make_movie("Inception")]
        use_case = _use_case(mocks)

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
        use_case = _use_case(mocks)

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
        use_case = _use_case(mocks)

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
        use_case = _use_case(mocks)

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="all", limit=4)
        )

        assert len(result) == 4

    @pytest.mark.asyncio
    async def test_should_return_empty_when_no_results(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = []
        mocks.series.find_random.return_value = []
        use_case = _use_case(mocks)

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="all", limit=10)
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_should_filter_with_backdrop(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = []
        use_case = _use_case(mocks)

        await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=5)
        )

        mocks.movies.find_random.assert_called_once_with(
            5,
            with_backdrop=True,
            allowed_library_ids=[_LIBRARY_ID],
            genres=[],
            exclude_ids=[],
        )

    @pytest.mark.asyncio
    async def test_should_pass_language_to_movie_outputs(self) -> None:
        movie = _make_movie("Inception")
        movie = movie.with_updates(
            localized={"pt-BR": {"title": "A Origem"}},
        )
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = [movie]
        use_case = _use_case(mocks)

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=1, lang="pt-BR")
        )

        assert result[0].title == "A Origem"

    @pytest.mark.asyncio
    async def test_movie_output_should_include_backdrop_and_genres(self) -> None:
        movie = _make_movie("Inception")
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = [movie]
        use_case = _use_case(mocks)

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
        use_case = _use_case(mocks)

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="series", limit=1)
        )

        assert result[0].duration_formatted is None
        assert result[0].year == 2008

    @pytest.mark.asyncio
    async def test_should_short_circuit_for_deny_all_profile(self) -> None:
        mocks = make_media_uow_mock()
        history = make_watch_history(titles=[_watched("mov_abc123def456", "movie")])
        use_case = _use_case(
            mocks,
            watch_history=history,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: []}),
        )

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="all", limit=10)
        )

        assert result == []
        assert history.calls == []
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
        use_case = _use_case(
            mocks,
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


@pytest.mark.unit
class TestGetFeaturedMediaRecommendations:
    """History-driven behaviour: exclude watched titles, prefer their genres."""

    @pytest.mark.asyncio
    async def test_no_history_should_not_touch_watched_lookups(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_random.return_value = [_make_movie("Random")]
        mocks.series.find_random.return_value = []
        use_case = _use_case(mocks)

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="all", limit=3)
        )

        assert [item.title for item in result] == ["Random"]
        mocks.movies.find_by_ids.assert_not_called()
        mocks.series.find_by_ids.assert_not_called()
        # Single draw per type — no genre filter, so no backfill round.
        assert mocks.movies.find_random.call_count == 1
        assert mocks.series.find_random.call_count == 1

    @pytest.mark.asyncio
    async def test_should_exclude_watched_movies_and_series_from_the_pool(self) -> None:
        watched_movie = _make_movie("Seen Movie", genres=["Action"])
        watched_series = _make_series("Seen Series", genres=["Drama"])
        mocks = make_media_uow_mock()
        mocks.movies.find_by_ids.return_value = {str(watched_movie.id): watched_movie}
        mocks.series.find_by_ids.return_value = {str(watched_series.id): watched_series}
        mocks.movies.find_random.return_value = [_make_movie("Fresh", genres=["Action"])]
        mocks.series.find_random.return_value = [_make_series("New Show", genres=["Drama"])]
        history = make_watch_history(
            titles=[
                _watched(str(watched_movie.id), "movie"),
                _watched(str(watched_series.id), "series", status="in_progress"),
            ]
        )
        use_case = _use_case(mocks, watch_history=history)

        await use_case.execute(GetFeaturedInput(profile_id=_PROFILE_ID, media_type="all", limit=1))

        movie_kwargs = mocks.movies.find_random.call_args_list[0].kwargs
        series_kwargs = mocks.series.find_random.call_args_list[0].kwargs
        assert movie_kwargs["exclude_ids"] == [watched_movie.id]
        assert series_kwargs["exclude_ids"] == [watched_series.id]

    @pytest.mark.asyncio
    async def test_should_prefer_top_genres_from_history(self) -> None:
        # Two completed Sci-Fi/Action movies, one abandoned Comedy: the
        # taste profile is Action > Sci-Fi > Comedy (weights 4, 4, 1).
        m1 = _make_movie("Interstellar", genres=["Sci-Fi", "Action"])
        m2 = _make_movie("Edge of Tomorrow", genres=["Action", "Sci-Fi"])
        m3 = _make_movie("Ted", genres=["Comedy"])
        mocks = make_media_uow_mock()
        mocks.movies.find_by_ids.return_value = {str(m.id): m for m in (m1, m2, m3)}
        mocks.series.find_by_ids.return_value = {}
        mocks.movies.find_random.return_value = [_make_movie("Dune", genres=["Sci-Fi"])]
        history = make_watch_history(
            titles=[
                _watched(str(m1.id), "movie"),
                _watched(str(m2.id), "movie"),
                _watched(str(m3.id), "movie", status="in_progress"),
            ]
        )
        use_case = _use_case(mocks, watch_history=history)

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=1)
        )

        assert [item.title for item in result] == ["Dune"]
        kwargs = mocks.movies.find_random.call_args_list[0].kwargs
        assert kwargs["genres"][:2] == [Genre("Sci-Fi"), Genre("Action")]
        assert Genre("Comedy") in kwargs["genres"]

    @pytest.mark.asyncio
    async def test_should_cap_taste_profile_at_top_three_genres(self) -> None:
        watched = _make_movie("Everything", genres=["A", "B", "C", "D", "E"])
        mocks = make_media_uow_mock()
        mocks.movies.find_by_ids.return_value = {str(watched.id): watched}
        mocks.series.find_by_ids.return_value = {}
        mocks.movies.find_random.return_value = [_make_movie("Pick")]
        history = make_watch_history(titles=[_watched(str(watched.id), "movie")])
        use_case = _use_case(mocks, watch_history=history)

        await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=1)
        )

        kwargs = mocks.movies.find_random.call_args_list[0].kwargs
        assert len(kwargs["genres"]) == 3

    @pytest.mark.asyncio
    async def test_should_backfill_with_unseen_titles_when_genre_pool_is_short(self) -> None:
        watched = _make_movie("Seen", genres=["Horror"])
        matched = _make_movie("Only Horror Left", genres=["Horror"])
        filler_a = _make_movie("Filler A", genres=["Romance"])
        filler_b = _make_movie("Filler B", genres=["Western"])
        mocks = make_media_uow_mock()
        mocks.movies.find_by_ids.return_value = {str(watched.id): watched}
        mocks.series.find_by_ids.return_value = {}
        mocks.movies.find_random.side_effect = [[matched], [filler_a, filler_b]]
        history = make_watch_history(titles=[_watched(str(watched.id), "movie")])
        use_case = _use_case(mocks, watch_history=history)

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=3)
        )

        # Genre match leads; backfill completes the banner.
        assert result[0].title == "Only Horror Left"
        assert {item.title for item in result[1:]} == {"Filler A", "Filler B"}

        first, second = mocks.movies.find_random.call_args_list
        assert first.args == (3,)
        assert first.kwargs["genres"] == [Genre("Horror")]
        assert first.kwargs["exclude_ids"] == [watched.id]
        # Backfill asks only for the missing slots, drops the genre
        # filter, and never re-draws the watched title or the match.
        assert second.args == (2,)
        assert second.kwargs["genres"] == []
        assert second.kwargs["exclude_ids"] == [watched.id, matched.id]

    @pytest.mark.asyncio
    async def test_should_not_backfill_when_genre_pool_fills_the_limit(self) -> None:
        watched = _make_movie("Seen", genres=["Horror"])
        mocks = make_media_uow_mock()
        mocks.movies.find_by_ids.return_value = {str(watched.id): watched}
        mocks.series.find_by_ids.return_value = {}
        mocks.movies.find_random.return_value = [
            _make_movie(f"Horror {i}", genres=["Horror"]) for i in range(2)
        ]
        history = make_watch_history(titles=[_watched(str(watched.id), "movie")])
        use_case = _use_case(mocks, watch_history=history)

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=2)
        )

        assert len(result) == 2
        assert mocks.movies.find_random.call_count == 1

    @pytest.mark.asyncio
    async def test_should_still_exclude_watched_when_history_titles_vanished(self) -> None:
        # The watched movie was deleted from the catalog: no genres to
        # learn from, but the id still must not come back (defensive).
        mocks = make_media_uow_mock()
        mocks.movies.find_by_ids.return_value = {}
        mocks.series.find_by_ids.return_value = {}
        mocks.movies.find_random.return_value = [_make_movie("Anything")]
        history = make_watch_history(titles=[_watched("mov_gone12345678", "movie")])
        use_case = _use_case(mocks, watch_history=history)

        result = await use_case.execute(
            GetFeaturedInput(profile_id=_PROFILE_ID, media_type="movie", limit=1)
        )

        assert [item.title for item in result] == ["Anything"]
        kwargs = mocks.movies.find_random.call_args_list[0].kwargs
        assert kwargs["genres"] == []
        assert [str(i) for i in kwargs["exclude_ids"]] == ["mov_gone12345678"]
        assert mocks.movies.find_random.call_count == 1


@pytest.mark.unit
class TestRankGenres:
    """The pure tallying helper behind the taste profile."""

    def test_should_weight_and_order_by_score(self) -> None:
        ranked = rank_genres(
            [
                ([Genre("Comedy")], 1),
                ([Genre("Action"), Genre("Sci-Fi")], 2),
                ([Genre("Sci-Fi")], 2),
            ],
            top_n=3,
        )

        assert ranked == [Genre("Sci-Fi"), Genre("Action"), Genre("Comedy")]

    def test_should_break_ties_by_first_seen(self) -> None:
        ranked = rank_genres([([Genre("Drama")], 1), ([Genre("Crime")], 1)], top_n=1)

        assert ranked == [Genre("Drama")]

    def test_should_return_empty_for_no_input(self) -> None:
        assert rank_genres([], top_n=3) == []
