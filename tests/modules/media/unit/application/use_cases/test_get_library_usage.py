"""Tests for GetLibraryUsageUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.application.use_cases.get_library_usage import (
    GetLibraryUsageUseCase,
)


def _uow_factory(
    movie_sizes: dict[str, int],
    episode_sizes: dict[str, int],
) -> MagicMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.movies.total_file_size_by_library.return_value = movie_sizes
    uow.series.episode_file_size_by_library.return_value = episode_sizes
    return MagicMock(return_value=uow)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_merges_movie_and_episode_sizes_sorted_desc() -> None:
    use_case = GetLibraryUsageUseCase(
        uow_factory=_uow_factory({"a": 100, "b": 50}, {"b": 200, "c": 30}),
    )

    out = await use_case.execute()

    # b = 50 + 200, a = 100, c = 30 — largest first.
    assert [(e.library_id, e.size_bytes) for e in out.libraries] == [
        ("b", 250),
        ("a", 100),
        ("c", 30),
    ]
    assert out.total_bytes == 380


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_catalog_yields_no_libraries() -> None:
    use_case = GetLibraryUsageUseCase(uow_factory=_uow_factory({}, {}))

    out = await use_case.execute()

    assert out.libraries == []
    assert out.total_bytes == 0
