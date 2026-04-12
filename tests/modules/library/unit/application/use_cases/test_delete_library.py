"""Tests for DeleteLibraryUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.library.application.dtos.library_dtos import DeleteLibraryInput
from src.modules.library.application.use_cases.delete_library import DeleteLibraryUseCase
from src.modules.library.domain.repositories.library_repository import LibraryRepository
from src.modules.library.domain.value_objects.library_id import LibraryId


@pytest.mark.unit
class TestDeleteLibraryUseCase:
    """Unit tests for deleting a library."""

    @pytest.mark.asyncio
    async def test_should_delete_when_found(self) -> None:
        repo = AsyncMock(spec=LibraryRepository)
        repo.delete.return_value = True
        use_case = DeleteLibraryUseCase(repo)
        lib_id = str(LibraryId.generate())

        await use_case.execute(DeleteLibraryInput(library_id=lib_id))

        repo.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_raise_when_not_found(self) -> None:
        repo = AsyncMock(spec=LibraryRepository)
        repo.delete.return_value = False
        use_case = DeleteLibraryUseCase(repo)
        lib_id = str(LibraryId.generate())

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(DeleteLibraryInput(library_id=lib_id))
