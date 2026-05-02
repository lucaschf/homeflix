"""Tests for ``GetCollectionByTmdbIdUseCase``."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.collection_dtos import (
    GetCollectionByTmdbIdInput,
)
from src.modules.media.application.ports import (
    CatalogRequestLookupPort,
    CatalogRequestStatus,
    CollectionDetailMetadata,
    CollectionPartMetadata,
    MetadataProvider,
)
from src.modules.media.application.use_cases.get_collection_by_tmdb_id import (
    GetCollectionByTmdbIdUseCase,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects import TmdbId
from tests.modules.media.unit.conftest import make_media_uow_mock


def _movie_with_tmdb(*, title: str, tmdb_id: int, year: int = 2010) -> Movie:
    movie = Movie.create(
        title=title,
        year=year,
        duration=8880,
        file_path=f"/movies/{title.lower()}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
    )
    return movie.with_updates(tmdb_id=TmdbId(tmdb_id))


def _make_metadata_provider(
    parts: list[CollectionPartMetadata],
) -> AsyncMock:
    provider = AsyncMock(spec=MetadataProvider)
    provider.get_collection.return_value = CollectionDetailMetadata(
        tmdb_id=8091,
        name="Alien Collection",
        overview="The saga.",
        poster_url="https://image.tmdb.org/p/poster.jpg",
        backdrop_url="https://image.tmdb.org/p/backdrop.jpg",
        parts=parts,
    )
    return provider


def _make_lookup_adapter(
    statuses: dict[int, CatalogRequestStatus] | None = None,
) -> AsyncMock:
    lookup = AsyncMock(spec=CatalogRequestLookupPort)
    lookup.get_for_movie_tmdb_ids.return_value = statuses or {}
    return lookup


class TestGetCollectionByTmdbIdUseCase:
    @pytest.mark.asyncio
    async def test_raises_when_collection_missing(self) -> None:
        mocks = make_media_uow_mock()
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_collection.return_value = None
        lookup = _make_lookup_adapter()

        use_case = GetCollectionByTmdbIdUseCase(mocks.factory, provider, lookup)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(GetCollectionByTmdbIdInput(tmdb_id=8091))

    @pytest.mark.asyncio
    async def test_marks_local_parts_as_in_catalog(self) -> None:
        parts = [
            CollectionPartMetadata(
                tmdb_id=348,
                title="Alien",
                year=1979,
                poster_url="https://image.tmdb.org/p/alien.jpg",
            ),
            CollectionPartMetadata(
                tmdb_id=679,
                title="Aliens",
                year=1986,
            ),
        ]
        mocks = make_media_uow_mock()
        # Only one part is hosted locally.
        mocks.movies.find_by_tmdb_ids.return_value = {
            348: _movie_with_tmdb(title="Alien", tmdb_id=348, year=1979),
        }
        provider = _make_metadata_provider(parts)
        lookup = _make_lookup_adapter()

        use_case = GetCollectionByTmdbIdUseCase(mocks.factory, provider, lookup)
        result = await use_case.execute(
            GetCollectionByTmdbIdInput(tmdb_id=8091),
        )

        assert result.total_parts == 2
        assert result.available_parts == 1
        assert result.missing_parts == 1
        # Sorted by year ASC: Alien (1979) before Aliens (1986).
        assert [p.tmdb_id for p in result.parts] == [348, 679]
        assert result.parts[0].in_catalog is True
        assert result.parts[0].movie_id is not None
        assert result.parts[1].in_catalog is False
        assert result.parts[1].movie_id is None

    @pytest.mark.asyncio
    async def test_surfaces_request_status_for_missing_parts_only(self) -> None:
        parts = [
            CollectionPartMetadata(tmdb_id=348, title="Alien", year=1979),
            CollectionPartMetadata(tmdb_id=679, title="Aliens", year=1986),
        ]
        mocks = make_media_uow_mock()
        mocks.movies.find_by_tmdb_ids.return_value = {
            348: _movie_with_tmdb(title="Alien", tmdb_id=348, year=1979),
        }
        provider = _make_metadata_provider(parts)
        # User has registered requests for BOTH parts. The use case
        # collapses ``in_catalog=True`` parts to no-request because
        # the UI doesn't show the request CTA there.
        lookup = _make_lookup_adapter(
            {
                348: CatalogRequestStatus(
                    is_requested=True,
                    notify_on_arrival=False,
                    is_fulfilled=False,
                ),
                679: CatalogRequestStatus(
                    is_requested=True,
                    notify_on_arrival=True,
                    is_fulfilled=False,
                ),
            },
        )

        use_case = GetCollectionByTmdbIdUseCase(mocks.factory, provider, lookup)
        result = await use_case.execute(GetCollectionByTmdbIdInput(tmdb_id=8091))

        in_catalog_part = next(p for p in result.parts if p.in_catalog)
        missing_part = next(p for p in result.parts if not p.in_catalog)
        assert in_catalog_part.is_requested is False
        assert in_catalog_part.notify_on_arrival is False
        assert missing_part.is_requested is True
        assert missing_part.notify_on_arrival is True

    @pytest.mark.asyncio
    async def test_pushes_unknown_year_parts_to_the_end(self) -> None:
        parts = [
            CollectionPartMetadata(tmdb_id=1, title="Future Sequel", year=None),
            CollectionPartMetadata(tmdb_id=2, title="Original", year=1979),
            CollectionPartMetadata(tmdb_id=3, title="Sequel", year=1986),
        ]
        mocks = make_media_uow_mock()
        mocks.movies.find_by_tmdb_ids.return_value = {}
        provider = _make_metadata_provider(parts)
        lookup = _make_lookup_adapter()

        use_case = GetCollectionByTmdbIdUseCase(mocks.factory, provider, lookup)
        result = await use_case.execute(GetCollectionByTmdbIdInput(tmdb_id=8091))

        assert [p.tmdb_id for p in result.parts] == [2, 3, 1]
