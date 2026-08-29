"""Tests for GetPersonBioUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.modules.metadata.application.ports.metadata_provider_port import PersonMetadata
from src.modules.metadata.application.use_cases.get_person_bio import (
    GetPersonBioInput,
    GetPersonBioUseCase,
    PersonBioOutput,
)


def _person(
    *,
    tmdb_id: int = 6193,
    name: str = "Leonardo DiCaprio",
    biography: str = "American actor.",
    birthday: str | None = "1974-11-11",
    deathday: str | None = None,
    place_of_birth: str | None = "Los Angeles, California, USA",
    known_for_department: str | None = "Acting",
    profile_path: str | None = "https://image.tmdb.org/t/p/original/leo.jpg",
) -> PersonMetadata:
    return PersonMetadata(
        tmdb_id=tmdb_id,
        name=name,
        biography=biography,
        birthday=birthday,
        deathday=deathday,
        place_of_birth=place_of_birth,
        known_for_department=known_for_department,
        profile_path=profile_path,
    )


@pytest.mark.unit
class TestGetPersonBioUseCase:
    """Tests for GetPersonBioUseCase."""

    @pytest.mark.asyncio
    async def test_should_map_provider_metadata_to_output(self) -> None:
        provider = AsyncMock()
        provider.get_person.return_value = _person()
        use_case = GetPersonBioUseCase(metadata_provider=provider)

        result = await use_case.execute(GetPersonBioInput(tmdb_id=6193))

        assert isinstance(result, PersonBioOutput)
        assert result.tmdb_id == 6193
        assert result.name == "Leonardo DiCaprio"
        assert result.biography == "American actor."
        assert result.birthday == "1974-11-11"
        assert result.known_for_department == "Acting"
        provider.get_person.assert_awaited_once_with(6193, language="en-US")

    @pytest.mark.asyncio
    async def test_should_forward_lang_to_provider(self) -> None:
        provider = AsyncMock()
        provider.get_person.return_value = _person()
        use_case = GetPersonBioUseCase(metadata_provider=provider)

        await use_case.execute(GetPersonBioInput(tmdb_id=6193, lang="pt-BR"))

        provider.get_person.assert_awaited_once_with(6193, language="pt-BR")

    @pytest.mark.asyncio
    async def test_should_return_none_when_provider_returns_none(self) -> None:
        # Network failure / 404 / unknown id all collapse to ``None`` at
        # the port — the actor page degrades to a name-only header.
        provider = AsyncMock()
        provider.get_person.return_value = None
        use_case = GetPersonBioUseCase(metadata_provider=provider)

        result = await use_case.execute(GetPersonBioInput(tmdb_id=99999999))

        assert result is None

    @pytest.mark.asyncio
    async def test_should_pass_tmdb_id_to_provider_unchanged(self) -> None:
        provider = AsyncMock()
        provider.get_person.return_value = _person(tmdb_id=12345)
        use_case = GetPersonBioUseCase(metadata_provider=provider)

        await use_case.execute(GetPersonBioInput(tmdb_id=12345))

        provider.get_person.assert_awaited_once_with(12345, language="en-US")
