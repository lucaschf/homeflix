"""Tests for DeleteLibraryUseCase."""

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.library.application.dtos.library_dtos import DeleteLibraryInput
from src.modules.library.application.use_cases.delete_library import DeleteLibraryUseCase
from src.modules.library.domain.value_objects.library_id import LibraryId
from tests.modules.library.unit.conftest import make_library_uow_mock


@pytest.mark.unit
class TestDeleteLibraryUseCase:
    """Unit tests for deleting a library."""

    @pytest.mark.asyncio
    async def test_should_delete_when_found(self) -> None:
        mocks = make_library_uow_mock()
        mocks.libraries.delete.return_value = True
        use_case = DeleteLibraryUseCase(uow_factory=mocks.factory)
        lib_id = str(LibraryId.generate())

        await use_case.execute(DeleteLibraryInput(library_id=lib_id))

        mocks.libraries.delete.assert_awaited_once()
        mocks.factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_when_not_found(self) -> None:
        mocks = make_library_uow_mock()
        mocks.libraries.delete.return_value = False
        use_case = DeleteLibraryUseCase(uow_factory=mocks.factory)
        lib_id = str(LibraryId.generate())

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(DeleteLibraryInput(library_id=lib_id))
