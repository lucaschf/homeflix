"""Unit test fixtures.

Fixtures for unit tests - no I/O, no external dependencies.
"""

import pytest

from src.domain.audit.value_objects import ApiCallId
from src.domain.collections.value_objects import FavoriteId, ListId, WatchlistId
from src.domain.media.value_objects import EpisodeId, MovieId, SeasonId, SeriesId
from src.domain.progress.value_objects import ProgressId


# Media IDs
@pytest.fixture
def sample_movie_id() -> MovieId:
    """Provide a sample MovieId for testing."""
    return MovieId("mov_abc123abc123")


@pytest.fixture
def sample_series_id() -> SeriesId:
    """Provide a sample SeriesId for testing."""
    return SeriesId("ser_xyz789xyz789")


@pytest.fixture
def sample_season_id() -> SeasonId:
    """Provide a sample SeasonId for testing."""
    return SeasonId("ssn_def456def456")


@pytest.fixture
def sample_episode_id() -> EpisodeId:
    """Provide a sample EpisodeId for testing."""
    return EpisodeId("epi_ghi789ghi789")


# Progress IDs
@pytest.fixture
def sample_progress_id() -> ProgressId:
    """Provide a sample ProgressId for testing."""
    return ProgressId("prg_jkl012jkl012")


# Collections IDs
@pytest.fixture
def sample_list_id() -> ListId:
    """Provide a sample ListId for testing."""
    return ListId("lst_mno345mno345")


@pytest.fixture
def sample_watchlist_id() -> WatchlistId:
    """Provide a sample WatchlistId for testing."""
    return WatchlistId("wls_pqr678pqr678")


@pytest.fixture
def sample_favorite_id() -> FavoriteId:
    """Provide a sample FavoriteId for testing."""
    return FavoriteId("fav_stu901stu901")


# Audit IDs
@pytest.fixture
def sample_api_call_id() -> ApiCallId:
    """Provide a sample ApiCallId for testing."""
    return ApiCallId("api_vwx234vwx234")


# Factories
@pytest.fixture
def movie_id_factory():
    """Factory to create MovieIds with optional custom values."""
    def _create(value: str | None = None) -> MovieId:
        if value:
            return MovieId(value)
        return MovieId.generate()
    return _create


@pytest.fixture
def series_id_factory():
    """Factory to create SeriesIds with optional custom values."""
    def _create(value: str | None = None) -> SeriesId:
        if value:
            return SeriesId(value)
        return SeriesId.generate()
    return _create


@pytest.fixture
def episode_id_factory():
    """Factory to create EpisodeIds with optional custom values."""
    def _create(value: str | None = None) -> EpisodeId:
        if value:
            return EpisodeId(value)
        return EpisodeId.generate()
    return _create


@pytest.fixture
def progress_id_factory():
    """Factory to create ProgressIds with optional custom values."""
    def _create(value: str | None = None) -> ProgressId:
        if value:
            return ProgressId(value)
        return ProgressId.generate()
    return _create