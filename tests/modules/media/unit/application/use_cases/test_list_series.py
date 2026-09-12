"""Tests for ListSeriesUseCase."""


import pytest

from src.building_blocks.domain.pagination import PaginatedResult, Pagination
from src.modules.media.application.dtos import (
    ListSeriesInput,
    ListSeriesOutput,
    SeriesSummaryOutput,
)
from src.modules.media.application.use_cases import ListSeriesUseCase
from src.modules.media.domain.entities import Series
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.library_id import LibraryId
from tests.modules.media.unit.conftest import (
    FakeProfileViewingPolicyPort,
    make_media_uow_mock,
    make_profile_viewing_policy,
)

_LIBRARY_ID = "lib_test12345678"
_LIBRARY_ID_OTHER = "lib_otherlibrary"
_PROFILE_ID = "prf_test12345678"


def _page(
    series_list: list[Series],
    *,
    next_cursor: str | None = None,
    has_more: bool = False,
    total_count: int | None = None,
) -> PaginatedResult[Series]:
    return PaginatedResult(
        items=series_list,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
        total_count=total_count,
    )


class TestListSeriesUseCase:
    """Tests for ListSeriesUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_first_page(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_paginated.return_value = _page(
            [
                Series.create(library_id=_LIBRARY_ID, title="Show 1", start_year=2020),
                Series.create(library_id=_LIBRARY_ID, title="Show 2", start_year=2021),
            ]
        )
        use_case = ListSeriesUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(ListSeriesInput(profile_id=_PROFILE_ID))

        assert isinstance(result, ListSeriesOutput)
        assert len(result.series) == 2
        assert result.has_more is False
        assert result.next_cursor is None
        assert result.total_count is None
        mocks.series.list_paginated.assert_awaited_once_with(
            cursor=None,
            limit=20,
            include_total=False,
            policy=ViewingPolicy.unrestricted([_LIBRARY_ID]),
            library_id=None,
            has_tmdb_id=None,
            q=None,
        )

    @pytest.mark.asyncio
    async def test_should_convert_series_to_summaries(self) -> None:
        mocks = make_media_uow_mock()
        series = Series.create(
            library_id=_LIBRARY_ID,
            title="Breaking Bad",
            start_year=2008,
            end_year=2013,
            genres=["Drama", "Crime"],
        )
        mocks.series.list_paginated.return_value = _page([series])
        use_case = ListSeriesUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(ListSeriesInput(profile_id=_PROFILE_ID))

        summary = result.series[0]
        assert isinstance(summary, SeriesSummaryOutput)
        assert summary.title == "Breaking Bad"
        assert summary.start_year == 2008
        assert summary.end_year == 2013
        assert summary.is_ongoing is False
        assert summary.genres == ["Drama", "Crime"]

    @pytest.mark.asyncio
    async def test_should_pass_cursor_and_limit_to_repository(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_paginated.return_value = _page([])
        use_case = ListSeriesUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        await use_case.execute(ListSeriesInput(profile_id=_PROFILE_ID, cursor="abc123", limit=15))

        mocks.series.list_paginated.assert_awaited_once_with(
            cursor="abc123",
            limit=15,
            include_total=False,
            policy=ViewingPolicy.unrestricted([_LIBRARY_ID]),
            library_id=None,
            has_tmdb_id=None,
            q=None,
        )

    @pytest.mark.asyncio
    async def test_should_propagate_next_cursor_and_has_more(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_paginated.return_value = _page(
            [Series.create(library_id=_LIBRARY_ID, title="Show 1", start_year=2020)],
            next_cursor="next-token",
            has_more=True,
        )
        use_case = ListSeriesUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(ListSeriesInput(profile_id=_PROFILE_ID))

        assert result.next_cursor == "next-token"
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_should_return_empty_page_when_no_series(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_paginated.return_value = _page([])
        use_case = ListSeriesUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(ListSeriesInput(profile_id=_PROFILE_ID))

        assert result.series == []
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_should_indicate_ongoing_series(self) -> None:
        mocks = make_media_uow_mock()
        series = Series.create(library_id=_LIBRARY_ID, title="Ongoing Show", start_year=2020)
        mocks.series.list_paginated.return_value = _page([series])
        use_case = ListSeriesUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(ListSeriesInput(profile_id=_PROFILE_ID))

        assert result.series[0].is_ongoing is True
        assert result.series[0].end_year is None

    @pytest.mark.asyncio
    async def test_should_include_season_and_episode_counts(self) -> None:
        mocks = make_media_uow_mock()
        series = Series.create(library_id=_LIBRARY_ID, title="Test Show", start_year=2020)
        mocks.series.list_paginated.return_value = _page([series])
        use_case = ListSeriesUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(ListSeriesInput(profile_id=_PROFILE_ID))

        assert result.series[0].season_count == 0
        assert result.series[0].total_episodes == 0
        assert result.series[0].intro_marked_count == 0

    @pytest.mark.asyncio
    async def test_should_request_total_when_include_total_is_true(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_paginated.return_value = _page(
            [Series.create(library_id=_LIBRARY_ID, title="Show 1", start_year=2020)],
            total_count=10,
        )
        use_case = ListSeriesUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=make_profile_viewing_policy(),
        )

        result = await use_case.execute(ListSeriesInput(profile_id=_PROFILE_ID, include_total=True))

        assert result.total_count == 10
        mocks.series.list_paginated.assert_awaited_once_with(
            cursor=None,
            limit=20,
            include_total=True,
            policy=ViewingPolicy.unrestricted([_LIBRARY_ID]),
            library_id=None,
            has_tmdb_id=None,
            q=None,
        )

    @pytest.mark.asyncio
    async def test_should_short_circuit_for_deny_all_profile(self) -> None:
        mocks = make_media_uow_mock()
        use_case = ListSeriesUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=FakeProfileViewingPolicyPort({_PROFILE_ID: []}),
        )

        result = await use_case.execute(ListSeriesInput(profile_id=_PROFILE_ID))

        assert result.series == []
        assert result.has_more is False
        assert result.next_cursor is None
        mocks.factory.assert_not_called()
        mocks.series.list_paginated.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_forward_only_allowed_libraries_for_inclusion_path(
        self,
    ) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_paginated.return_value = _page(
            [Series.create(library_id=_LIBRARY_ID, title="Visible", start_year=2020)]
        )
        use_case = ListSeriesUseCase(
            uow_factory=mocks.factory,
            profile_viewing_policy=FakeProfileViewingPolicyPort({_PROFILE_ID: [_LIBRARY_ID]}),
        )

        result = await use_case.execute(ListSeriesInput(profile_id=_PROFILE_ID))

        assert [s.title for s in result.series] == ["Visible"]
        passed = mocks.series.list_paginated.await_args.kwargs["policy"]
        assert passed == ViewingPolicy.unrestricted([_LIBRARY_ID])
        assert not passed.permits_library(LibraryId(_LIBRARY_ID_OTHER))
