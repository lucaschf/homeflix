"""Tests for GetLibraryByIdUseCase."""

from unittest.mock import AsyncMock

import pytest
from tests.modules.library.unit.conftest import make_library_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.library.application.dtos.library_dtos import GetLibraryByIdInput
from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.application.use_cases.get_library_by_id import (
    GetLibraryByIdUseCase,
)
from src.modules.library.domain.entities.library import Library
from src.shared_kernel.value_objects.library_id import LibraryId


def _make_media_count_query() -> AsyncMock:
    query = AsyncMock(spec=MediaCountQueryPort)
    query.count_movies_under_paths.return_value = 0
    query.count_series_under_paths.return_value = 0
    return query


@pytest.mark.unit
class TestGetLibraryByIdUseCase:
    """Unit tests for fetching a library by id."""

    @pytest.mark.asyncio
    async def test_should_return_library_when_found(self) -> None:
        lib = Library.create(name="Movies", library_type="movies", paths=["/m"])
        mocks = make_library_uow_mock()
        mocks.libraries.find_by_id.return_value = lib
        use_case = GetLibraryByIdUseCase(mocks.factory, _make_media_count_query())

        result = await use_case.execute(
            GetLibraryByIdInput(library_id=str(lib.id)),
        )

        assert result.name == "Movies"

    @pytest.mark.asyncio
    async def test_should_raise_when_not_found(self) -> None:
        mocks = make_library_uow_mock()
        mocks.libraries.find_by_id.return_value = None
        use_case = GetLibraryByIdUseCase(mocks.factory, _make_media_count_query())
        lib_id = str(LibraryId.generate())

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetLibraryByIdInput(library_id=lib_id),
            )
