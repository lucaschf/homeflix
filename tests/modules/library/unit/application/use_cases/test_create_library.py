"""Tests for CreateLibraryUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.modules.library.application.dtos.library_dtos import CreateLibraryInput
from src.modules.library.application.use_cases.create_library import CreateLibraryUseCase
from src.modules.library.domain.repositories.library_repository import LibraryRepository


def _make_repo() -> AsyncMock:
    repo = AsyncMock(spec=LibraryRepository)
    # save echoes back whatever it receives
    repo.save.side_effect = lambda lib: lib
    return repo


@pytest.mark.unit
class TestCreateLibraryUseCase:
    """Unit tests for library creation."""

    @pytest.mark.asyncio
    async def test_should_create_library_with_generated_id(self) -> None:
        repo = _make_repo()
        use_case = CreateLibraryUseCase(repo)

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
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_pass_settings_through(self) -> None:
        repo = _make_repo()
        use_case = CreateLibraryUseCase(repo)

        result = await use_case.execute(
            CreateLibraryInput(
                name="Anime",
                library_type="series",
                paths=["/media/anime"],
                language="ja",
                settings={
                    "preferred_audio_language": "ja",
                    "preferred_subtitle_language": "en",
                    "subtitle_mode": "always",
                },
            )
        )

        assert result.settings.preferred_audio_language == "ja"
        assert result.settings.preferred_subtitle_language == "en"
        assert result.settings.subtitle_mode == "always"

    @pytest.mark.asyncio
    async def test_should_pass_metadata_providers(self) -> None:
        repo = _make_repo()
        use_case = CreateLibraryUseCase(repo)

        result = await use_case.execute(
            CreateLibraryInput(
                name="Movies",
                library_type="movies",
                paths=["/media/movies"],
                metadata_providers=[
                    {"provider": "tmdb", "priority": 1},
                    {"provider": "omdb", "priority": 2, "enabled": False},
                ],
            )
        )

        assert len(result.metadata_providers) == 2
        assert result.metadata_providers[0].provider == "tmdb"
        assert result.metadata_providers[1].enabled is False
