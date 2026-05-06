"""Tests for ListRecentlyAddedSeriesUseCase."""

import pytest

from src.modules.media.application.dtos import (
    ListRecentlyAddedSeriesInput,
    ListRecentlyAddedSeriesOutput,
    SeriesSummaryOutput,
)
from src.modules.media.application.use_cases import ListRecentlyAddedSeriesUseCase
from src.modules.media.domain.entities import Series
from tests.modules.media.unit.conftest import (
    FakeProfileLibraryAccessPort,
    make_media_uow_mock,
    make_profile_library_access,
)

_LIBRARY_ID = "lib_test12345678"
_LIBRARY_ID_OTHER = "lib_otherlibrary"
_PROFILE_ID = "prf_test12345678"


def _make_series(
    title: str = "Test Series", year: int = 2020, *, library_id: str = _LIBRARY_ID
) -> Series:
    return Series.create(library_id=library_id, title=title, start_year=year)


class TestListRecentlyAddedSeriesUseCase:
    """Tests for ListRecentlyAddedSeriesUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_summaries_in_repository_order(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_recently_added.return_value = [
            _make_series("Newest"),
            _make_series("Older"),
        ]
        use_case = ListRecentlyAddedSeriesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            ListRecentlyAddedSeriesInput(profile_id=_PROFILE_ID, limit=10)
        )

        assert isinstance(result, ListRecentlyAddedSeriesOutput)
        assert [s.title for s in result.series] == ["Newest", "Older"]
        assert all(isinstance(s, SeriesSummaryOutput) for s in result.series)

    @pytest.mark.asyncio
    async def test_should_pass_limit_to_repository(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_recently_added.return_value = []
        use_case = ListRecentlyAddedSeriesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        await use_case.execute(ListRecentlyAddedSeriesInput(profile_id=_PROFILE_ID, limit=15))

        mocks.series.list_recently_added.assert_awaited_once_with(
            15, allowed_library_ids=[_LIBRARY_ID]
        )

    @pytest.mark.asyncio
    async def test_should_default_limit_to_twenty(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_recently_added.return_value = []
        use_case = ListRecentlyAddedSeriesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        await use_case.execute(ListRecentlyAddedSeriesInput(profile_id=_PROFILE_ID))

        mocks.series.list_recently_added.assert_awaited_once_with(
            20, allowed_library_ids=[_LIBRARY_ID]
        )

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_repository_empty(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_recently_added.return_value = []
        use_case = ListRecentlyAddedSeriesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(ListRecentlyAddedSeriesInput(profile_id=_PROFILE_ID))

        assert result.series == []

    @pytest.mark.asyncio
    async def test_should_short_circuit_for_deny_all_profile(self) -> None:
        mocks = make_media_uow_mock()
        use_case = ListRecentlyAddedSeriesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: []}),
        )

        result = await use_case.execute(ListRecentlyAddedSeriesInput(profile_id=_PROFILE_ID))

        assert result.series == []
        mocks.factory.assert_not_called()
        mocks.series.list_recently_added.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_forward_only_allowed_libraries_for_inclusion_path(
        self,
    ) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_recently_added.return_value = [
            _make_series("Visible", library_id=_LIBRARY_ID)
        ]
        use_case = ListRecentlyAddedSeriesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: [_LIBRARY_ID]}),
        )

        result = await use_case.execute(ListRecentlyAddedSeriesInput(profile_id=_PROFILE_ID))

        assert [s.title for s in result.series] == ["Visible"]
        passed = mocks.series.list_recently_added.await_args.kwargs["allowed_library_ids"]
        assert list(passed) == [_LIBRARY_ID]
        assert _LIBRARY_ID_OTHER not in list(passed)
