"""Tests for GetLibraryByIdUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.library.application.dtos.library_dtos import GetLibraryByIdInput
from src.modules.library.application.use_cases.get_library_by_id import (
    GetLibraryByIdUseCase,
)
from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.repositories.library_repository import LibraryRepository
from src.modules.library.domain.value_objects.library_id import LibraryId


@pytest.mark.unit
class TestGetLibraryByIdUseCase:
    """Unit tests for fetching a library by id."""

    @pytest.mark.asyncio
    async def test_should_return_library_when_found(self) -> None:
        lib = Library.create(name="Movies", library_type="movies", paths=["/m"])
        repo = AsyncMock(spec=LibraryRepository)
        repo.find_by_id.return_value = lib
        use_case = GetLibraryByIdUseCase(repo)

        result = await use_case.execute(
            GetLibraryByIdInput(library_id=str(lib.id)),
        )

        assert result.name == "Movies"

    @pytest.mark.asyncio
    async def test_should_raise_when_not_found(self) -> None:
        repo = AsyncMock(spec=LibraryRepository)
        repo.find_by_id.return_value = None
        use_case = GetLibraryByIdUseCase(repo)
        lib_id = str(LibraryId.generate())

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetLibraryByIdInput(library_id=lib_id),
            )
