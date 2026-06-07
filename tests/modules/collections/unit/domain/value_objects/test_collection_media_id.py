"""Tests for the CollectionMediaId value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId


class TestCollectionMediaIdMovie:
    """Movie-shaped ids."""

    def test_accepts_valid_movie_id(self):
        media_id = CollectionMediaId("mov_2xK9mPqR7nL4")

        assert media_id.value == "mov_2xK9mPqR7nL4"
        assert media_id.is_movie is True
        assert media_id.is_series is False

    def test_as_movie_id_returns_typed_id(self):
        assert CollectionMediaId("mov_2xK9mPqR7nL4").as_movie_id() == MovieId("mov_2xK9mPqR7nL4")

    def test_rejects_malformed_movie_id(self):
        with pytest.raises(DomainValidationException):
            CollectionMediaId("mov_short")


class TestCollectionMediaIdSeries:
    """Series-shaped ids."""

    def test_accepts_valid_series_id(self):
        media_id = CollectionMediaId("ser_3yL8nQsT9mK5")

        assert media_id.is_series is True
        assert media_id.is_movie is False

    def test_as_series_id_returns_typed_id(self):
        assert CollectionMediaId("ser_3yL8nQsT9mK5").as_series_id() == SeriesId("ser_3yL8nQsT9mK5")

    def test_rejects_malformed_series_id(self):
        with pytest.raises(DomainValidationException):
            CollectionMediaId("ser_bad")


class TestCollectionMediaIdRejections:
    """Shapes that don't belong in a collection."""

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "garbage",
            "ssn_4zM9oPtU0nL6",  # season — not a whole title
            "epi_5aH0pQuV1oM7",  # episode — not a whole title
            "epi_ser_3yL8nQsT9mK5_1_2",  # composite episode id
            "lib_2xK9mPqR7nL4",
        ],
    )
    def test_rejects_invalid_shapes(self, value: str):
        with pytest.raises(DomainValidationException):
            CollectionMediaId(value)
