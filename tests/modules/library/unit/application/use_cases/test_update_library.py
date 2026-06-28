"""Tests for UpdateLibraryUseCase."""

from unittest.mock import AsyncMock

import pytest
from tests.modules.library.unit.conftest import make_library_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.library.application.dtos.library_dtos import UpdateLibraryInput
from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.application.use_cases.update_library import UpdateLibraryUseCase
from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.value_objects.library_settings import LibrarySettings
from src.modules.library.domain.value_objects.library_type import LibraryType
from src.modules.library.domain.value_objects.metadata_provider import (
    MetadataProvider,
    MetadataProviderConfig,
)
from src.modules.library.domain.value_objects.subtitle_mode import SubtitleMode
from src.shared_kernel.value_objects.language_code import LanguageCode


def _existing_library() -> Library:
    return Library.create(
        name="Movies",
        library_type=LibraryType.MOVIES,
        paths=["/media/movies"],
        metadata_providers=[MetadataProviderConfig.tmdb()],
    )


def _configure(existing: Library | None) -> "tuple[UpdateLibraryUseCase, AsyncMock]":
    mocks = make_library_uow_mock()
    mocks.libraries.find_by_id.return_value = existing
    mocks.libraries.save.side_effect = lambda lib: lib

    media_count_query = AsyncMock(spec=MediaCountQueryPort)
    media_count_query.count_movies_under_paths.return_value = 0
    media_count_query.count_series_under_paths.return_value = 0

    use_case = UpdateLibraryUseCase(
        uow_factory=mocks.factory,
        media_count_query=media_count_query,
    )
    return use_case, mocks.libraries.save


@pytest.mark.unit
class TestUpdateLibraryUseCase:
    """Unit tests for partial library updates."""

    @pytest.mark.asyncio
    async def test_raises_when_library_missing(self) -> None:
        use_case, _ = _configure(existing=None)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(UpdateLibraryInput(library_id="lib_doesnotexist"))

    @pytest.mark.asyncio
    async def test_updates_only_supplied_fields(self) -> None:
        existing = _existing_library()
        use_case, save = _configure(existing)

        result = await use_case.execute(
            UpdateLibraryInput(
                library_id=str(existing.id),
                name="Renamed",
            )
        )

        assert result.name == "Renamed"
        # Untouched fields keep their previous value.
        assert result.library_type == "movies"
        assert result.paths == ["/media/movies"]
        save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_applies_typed_metadata_providers_and_settings(self) -> None:
        existing = _existing_library()
        use_case, _ = _configure(existing)

        result = await use_case.execute(
            UpdateLibraryInput(
                library_id=str(existing.id),
                metadata_providers=[
                    MetadataProviderConfig(provider=MetadataProvider.OMDB, priority=1),
                ],
                settings=LibrarySettings(
                    preferred_audio_language=LanguageCode("ja"),
                    subtitle_mode=SubtitleMode.ALWAYS,
                ),
                scan_schedule="0 4 * * *",
            )
        )

        assert len(result.metadata_providers) == 1
        assert result.metadata_providers[0].provider == "omdb"
        assert result.settings.preferred_audio_language == "ja"
        assert result.settings.subtitle_mode == "always"
        assert result.scan_schedule == "0 4 * * *"

    @pytest.mark.asyncio
    async def test_rejects_invalid_scan_schedule(self) -> None:
        from src.building_blocks.domain.errors import DomainValidationException

        existing = _existing_library()
        use_case, _ = _configure(existing)

        with pytest.raises(DomainValidationException):
            await use_case.execute(
                UpdateLibraryInput(
                    library_id=str(existing.id),
                    scan_schedule="99 99 99 99 99",
                )
            )
