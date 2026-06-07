"""Collection media identifier value object."""

from __future__ import annotations

from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain.errors import DomainValidationException
from src.building_blocks.domain.value_objects import StringValueObject
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId


class CollectionMediaId(StringValueObject):
    """Identifier of a catalog entry that can be saved to a collection.

    Watchlist entries and custom-list items reference whole catalog
    titles — a movie (``mov_xxx``) or a series (``ser_xxx``) — never a
    season or an episode. Anything else (empty strings, season/episode
    prefixes, malformed ids) fails on construction so garbage can no
    longer round-trip to the database.

    Example:
        >>> CollectionMediaId("mov_2xK9mPqR7nL4").is_movie
        True
        >>> CollectionMediaId("ser_3yL8nQsT9mK5").as_series_id().value
        'ser_3yL8nQsT9mK5'
    """

    _RULE_CODE: ClassVar[str] = "COLLECTIONS.MEDIA_ID.INVALID"

    @model_validator(mode="before")
    @classmethod
    def _validate(cls, value: str) -> str:
        """Accept a movie or series id, reject everything else."""
        if not isinstance(value, str):
            raise ValueError("Collection media id must be a string")

        value = value.strip()
        if value.startswith("mov_"):
            cls._ensure_valid(MovieId, value)
        elif value.startswith("ser_"):
            cls._ensure_valid(SeriesId, value)
        else:
            raise ValueError(
                f"Invalid collection media id: '{value}'. Expected 'mov_xxx' or "
                f"'ser_xxx' [{cls._RULE_CODE}]"
            )
        return value

    @classmethod
    def _ensure_valid(cls, id_type: type[MovieId | SeriesId], value: str) -> None:
        try:
            id_type(value)
        except DomainValidationException as exc:
            raise ValueError(
                f"Invalid {id_type.__name__} for collection: '{value}' [{cls._RULE_CODE}]"
            ) from exc

    @property
    def is_movie(self) -> bool:
        """``True`` when the id points at a movie (``mov_xxx``)."""
        return self.value.startswith("mov_")

    @property
    def is_series(self) -> bool:
        """``True`` when the id points at a series (``ser_xxx``)."""
        return self.value.startswith("ser_")

    def as_movie_id(self) -> MovieId:
        """Return the id as a typed :class:`MovieId`.

        Raises:
            DomainValidationException: When the id is a series id.
        """
        return MovieId(self.value)

    def as_series_id(self) -> SeriesId:
        """Return the id as a typed :class:`SeriesId`.

        Raises:
            DomainValidationException: When the id is a movie id.
        """
        return SeriesId(self.value)


__all__ = ["CollectionMediaId"]
