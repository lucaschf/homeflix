"""Shared fixtures for collections use case tests."""

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from src.modules.collections.application.ports import (
    MediaLookupPort,
    MediaSummary,
    ProfileLookupPort,
    ProfileViewingPolicyPort,
    ProgressLookupPort,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.library_id import LibraryId

MediaSummaryFactory = Callable[..., MediaSummary]

#: Libraries the summary factories place titles in by default.
MOVIES_LIBRARY_ID = "lib_movies000001"
SERIES_LIBRARY_ID = "lib_series000001"


@pytest.fixture
def movie_summary() -> MediaSummaryFactory:
    """Create a ``MediaSummary`` representing a movie."""

    def _factory(
        media_id: str,
        title: str = "Test Movie",
        poster_path: str | None = "https://image.tmdb.org/poster.jpg",
        year: int | None = 2010,
        runtime_seconds: int | None = 8880,
        genres: tuple[str, ...] = ("Action", "Sci-Fi"),
        resolution: str | None = "4K",
        hdr: bool = True,
        library_id: str | None = MOVIES_LIBRARY_ID,
        minimum_age: AgeRating | None = None,
    ) -> MediaSummary:
        return MediaSummary(
            media_id=media_id,
            media_type=MediaType.MOVIE,
            title=title,
            poster_path=poster_path,
            year=year,
            runtime_seconds=runtime_seconds,
            genres=genres,
            resolution=resolution,
            hdr=hdr,
            library_id=library_id,
            minimum_age=minimum_age,
        )

    return _factory


@pytest.fixture
def series_summary() -> MediaSummaryFactory:
    """Create a ``MediaSummary`` representing a series."""

    def _factory(
        media_id: str,
        title: str = "Test Series",
        poster_path: str | None = "https://image.tmdb.org/series.jpg",
        year: int | None = 2008,
        genres: tuple[str, ...] = ("Drama",),
        library_id: str | None = SERIES_LIBRARY_ID,
        minimum_age: AgeRating | None = None,
    ) -> MediaSummary:
        return MediaSummary(
            media_id=media_id,
            media_type=MediaType.SERIES,
            title=title,
            poster_path=poster_path,
            year=year,
            genres=genres,
            library_id=library_id,
            minimum_age=minimum_age,
        )

    return _factory


def make_media_lookup_mock(*summaries: MediaSummary) -> AsyncMock:
    """Build an ``AsyncMock`` of ``MediaLookupPort`` returning ``summaries``."""
    mock = AsyncMock(spec=MediaLookupPort)
    mock.get_many.return_value = {(s.media_type, s.media_id): s for s in summaries}
    return mock


def make_visible_titles_lookup_mock(*visible_ids: str) -> AsyncMock:
    """Build an ``AsyncMock`` of ``MediaLookupPort`` whose catalog sees only ``visible_ids``.

    ``find_visible_titles`` answers with the requested ids that are in
    ``visible_ids``; every other id — missing or hidden alike — is absent.
    """
    mock = AsyncMock(spec=MediaLookupPort)
    visible = frozenset(visible_ids)

    async def find_visible_titles(*, movie_ids, series_ids, policy):
        requested = {m.value for m in movie_ids} | {s.value for s in series_ids}
        return frozenset(requested & visible)

    mock.find_visible_titles.side_effect = find_visible_titles
    return mock


def make_catalog_lookup_mock(*summaries: MediaSummary) -> AsyncMock:
    """Build an ``AsyncMock`` of ``MediaLookupPort`` over one consistent catalog.

    ``get_many`` answers with ``summaries``; ``find_visible_titles`` answers
    with the requested ids whose summary ``policy.permits``. Reads that use
    either method therefore agree on which titles exist, which the policy
    reaches by library and which its maturity limit withholds.
    """
    mock = make_media_lookup_mock(*summaries)
    by_id = {s.media_id: s for s in summaries}

    async def find_visible_titles(*, movie_ids, series_ids, policy):
        requested = [m.value for m in movie_ids] + [s.value for s in series_ids]
        return frozenset(
            media_id
            for media_id in requested
            if (summary := by_id.get(media_id)) is not None
            and summary.library_id is not None
            and policy.permits(
                library_id=LibraryId(summary.library_id), minimum_age=summary.minimum_age
            )
        )

    mock.find_visible_titles.side_effect = find_visible_titles
    return mock


def make_progress_lookup_mock(progress: dict[str, float] | None = None) -> AsyncMock:
    """Build an ``AsyncMock`` of ``ProgressLookupPort`` returning ``progress``."""
    mock = AsyncMock(spec=ProgressLookupPort)
    mock.get_progress.return_value = progress or {}
    return mock


def make_profile_viewing_policy_mock(
    *library_ids: str, maturity_limit: AgeRating | None = None
) -> AsyncMock:
    """Build an ``AsyncMock`` of ``ProfileViewingPolicyPort``.

    Returns a ``ViewingPolicy`` over the given ids, with the given
    maturity limit (none by default), for any profile. No ids means
    deny-all.
    """
    mock = AsyncMock(spec=ProfileViewingPolicyPort)
    mock.find_for_profile.return_value = ViewingPolicy(
        allowed_library_ids=library_ids, maturity_limit=maturity_limit
    )
    return mock


def make_profile_lookup_mock(names: dict[str, str] | None = None) -> AsyncMock:
    """Build an ``AsyncMock`` of ``ProfileLookupPort`` returning ``names``."""
    mock = AsyncMock(spec=ProfileLookupPort)
    mock.get_names.return_value = names or {}
    return mock
