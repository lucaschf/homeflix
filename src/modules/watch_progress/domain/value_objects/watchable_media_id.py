"""Watchable media identifier value object."""

from __future__ import annotations

from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain.errors import DomainValidationException
from src.building_blocks.domain.value_objects import StringValueObject
from src.shared_kernel.value_objects.episode_composite_id import EpisodeCompositeId
from src.shared_kernel.value_objects.media_id import MovieId


class WatchableMediaId(StringValueObject):
    """Identifier of something a profile can watch.

    Watch progress rows point at exactly two shapes of identifier:

    - ``mov_{base62_12chars}`` — a movie external id.
    - ``epi_{ser_xxx}_{season}_{episode}`` — the composite episode id
      built by :class:`EpisodeCompositeId` (the frontend contract for
      episode playback). Plain ``epi_{base62}`` catalog episode ids are
      **not** accepted — the player never sends them.

    Anything else (empty strings, wrong prefixes, malformed composites)
    fails on construction, so garbage can no longer round-trip to the
    database and silently vanish from Continue Watching.

    Example:
        >>> WatchableMediaId("mov_2xK9mPqR7nL4").is_movie
        True
        >>> WatchableMediaId("epi_ser_3yL8nQsT9mK5_1_2").as_episode().episode_number
        2
    """

    _RULE_CODE: ClassVar[str] = "WATCH_PROGRESS.MEDIA_ID.INVALID"

    @model_validator(mode="before")
    @classmethod
    def _validate(cls, value: str) -> str:
        """Accept a movie id or a composite episode id, reject the rest."""
        if not isinstance(value, str):
            raise ValueError("Watchable media id must be a string")

        value = value.strip()
        if value.startswith("mov_"):
            try:
                MovieId(value)
            except DomainValidationException as exc:
                raise ValueError(
                    f"Invalid movie id for watch progress: '{value}' [{cls._RULE_CODE}]"
                ) from exc
            return value

        try:
            parsed = EpisodeCompositeId.parse(value)
        except DomainValidationException as exc:
            raise ValueError(
                f"Malformed composite episode id: '{value}' [{cls._RULE_CODE}]"
            ) from exc
        if parsed is not None:
            return value

        raise ValueError(
            f"Invalid watchable media id: '{value}'. Expected 'mov_xxx' or "
            f"'epi_ser_xxx_S_E' [{cls._RULE_CODE}]"
        )

    @property
    def is_movie(self) -> bool:
        """``True`` when the id points at a movie (``mov_xxx``)."""
        return self.value.startswith("mov_")

    @property
    def is_episode(self) -> bool:
        """``True`` when the id is a composite episode id."""
        return not self.is_movie

    def as_movie_id(self) -> MovieId:
        """Return the id as a typed :class:`MovieId`.

        Raises:
            DomainValidationException: When the id is an episode id.
        """
        return MovieId(self.value)

    def as_episode(self) -> EpisodeCompositeId:
        """Return the parsed :class:`EpisodeCompositeId`.

        Raises:
            ValueError: When the id is a movie id.
        """
        parsed = EpisodeCompositeId.parse(self.value)
        if parsed is None:
            raise ValueError(f"Not a composite episode id: '{self.value}'")
        return parsed


__all__ = ["WatchableMediaId"]
