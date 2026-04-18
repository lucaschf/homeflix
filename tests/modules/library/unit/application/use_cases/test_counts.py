"""Tests for the ``resolve_counts`` helper."""

from unittest.mock import AsyncMock

import pytest

from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.application.use_cases._counts import resolve_counts
from src.modules.library.domain.entities.library import Library


@pytest.mark.unit
class TestResolveCounts:
    @pytest.mark.asyncio
    async def test_should_issue_both_counts_with_entity_paths(self) -> None:
        lib = Library.create(
            name="Mixed",
            library_type="mixed",
            paths=["/media/movies", "/media/shows"],
        )
        query = AsyncMock(spec_set=MediaCountQueryPort)
        query.count_movies_under_paths.return_value = 12
        query.count_series_under_paths.return_value = 3

        movie_count, series_count = await resolve_counts(lib, query)

        assert (movie_count, series_count) == (12, 3)
        query.count_movies_under_paths.assert_awaited_once_with(["/media/movies", "/media/shows"])
        query.count_series_under_paths.assert_awaited_once_with(["/media/movies", "/media/shows"])
