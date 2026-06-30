"""Tests for CreateLibraryUseCase."""

from unittest.mock import AsyncMock

import pytest
from tests.modules.library.unit.conftest import make_library_uow_mock

from src.modules.library.application.dtos.library_dtos import CreateLibraryInput
from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.application.use_cases.create_library import CreateLibraryUseCase
from src.modules.library.domain.value_objects.library_settings import LibrarySettings
from src.modules.library.domain.value_objects.metadata_provider import (
    MetadataProvider,
    MetadataProviderConfig,
)


def _configure_uow_mocks() -> "tuple[CreateLibraryUseCase, object, object]":
    mocks = make_library_uow_mock()
    mocks.libraries.save.side_effect = lambda lib: lib

    media_count_query = AsyncMock(spec=MediaCountQueryPort)
    media_count_query.count_movies_under_paths.return_value = 0
    media_count_query.count_series_under_paths.return_value = 0

    use_case = CreateLibraryUseCase(
        uow_factory=mocks.factory,
        media_count_query=media_count_query,
    )
    return use_case, mocks.libraries.save, mocks.factory


@pytest.mark.unit
class TestCreateLibraryUseCase:
    """Unit tests for library creation."""

    @pytest.mark.asyncio
    async def test_should_create_library_with_generated_id(self) -> None:
        use_case, save, factory = _configure_uow_mocks()

        result = await use_case.execute(
            CreateLibraryInput(
                name="Movies",
                library_type="movies",
                paths=["/media/movies"],
            )
        )

        assert result.name == "Movies"
        assert result.library_type == "movies"
        assert result.paths == ["/media/movies"]
        assert result.id.startswith("lib_")
        save.assert_awaited_once()
        factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_pass_settings_through(self) -> None:
        use_case, _, _ = _configure_uow_mocks()

        result = await use_case.execute(
            CreateLibraryInput(
                name="Anime",
                library_type="series",
                paths=["/media/anime"],
                language="ja",
                settings=LibrarySettings(
                    generate_thumbnails=False,
                    detect_intros=True,
                ),
            )
        )

        assert result.settings.generate_thumbnails is False
        assert result.settings.detect_intros is True

    @pytest.mark.asyncio
    async def test_should_pass_metadata_providers(self) -> None:
        use_case, _, _ = _configure_uow_mocks()

        result = await use_case.execute(
            CreateLibraryInput(
                name="Movies",
                library_type="movies",
                paths=["/media/movies"],
                metadata_providers=[
                    MetadataProviderConfig(provider=MetadataProvider.TMDB, priority=1),
                    MetadataProviderConfig(
                        provider=MetadataProvider.OMDB, priority=2, enabled=False
                    ),
                ],
            )
        )

        assert len(result.metadata_providers) == 2
        assert result.metadata_providers[0].provider == "tmdb"
        assert result.metadata_providers[1].enabled is False
