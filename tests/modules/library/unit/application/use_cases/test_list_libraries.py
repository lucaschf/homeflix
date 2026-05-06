"""Tests for ListLibrariesUseCase."""

from unittest.mock import AsyncMock

import pytest
from tests.modules.library.unit.conftest import make_library_uow_mock

from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.application.use_cases.list_libraries import ListLibrariesUseCase
from src.modules.library.domain.entities.library import Library


def _make_media_count_query() -> AsyncMock:
    query = AsyncMock(spec=MediaCountQueryPort)
    query.count_movies_under_paths.return_value = 0
    query.count_series_under_paths.return_value = 0
    return query


@pytest.mark.unit
class TestListLibrariesUseCase:
    """Unit tests for listing libraries."""

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_libraries(self) -> None:
        mocks = make_library_uow_mock()
        mocks.libraries.find_all.return_value = []
        use_case = ListLibrariesUseCase(mocks.factory, _make_media_count_query())

        result = await use_case.execute()

        assert result == []

    @pytest.mark.asyncio
    async def test_should_return_all_libraries(self) -> None:
        mocks = make_library_uow_mock()
        mocks.libraries.find_all.return_value = [
            Library.create(name="Movies", library_type="movies", paths=["/m"]),
            Library.create(name="Series", library_type="series", paths=["/s"]),
        ]
        use_case = ListLibrariesUseCase(mocks.factory, _make_media_count_query())

        result = await use_case.execute()

        assert len(result) == 2
        assert result[0].name == "Movies"
        assert result[1].name == "Series"
