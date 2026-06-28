"""Shared helper for composite episode media IDs.

The frontend identifies episodes using composite keys in the format
``epi_{series_id}_{season_number}_{episode_number}`` (e.g.
``epi_ser_Hy9VjMfILYZe_3_2``). This module is the single place where
that wire format is defined, built and parsed, so the scheme never has
to be reconstructed by hand elsewhere.
"""

from __future__ import annotations

from enum import StrEnum

from src.building_blocks.domain.errors import DomainValidationException
from src.building_blocks.domain.value_objects import CompoundValueObject
from src.shared_kernel.value_objects.media_id import SeriesId

# Marker that precedes the series id in every composite key. Derived from
# ``SeriesId.EXPECTED_PREFIX`` so the ``ser`` scheme lives in one place
# (``media_id.py``) instead of being duplicated as a literal here.
_PREFIX = "epi_"
_COMPOSITE_MARKER = f"{_PREFIX}{SeriesId.EXPECTED_PREFIX}_"


class EpisodeCompositeIdRuleCodes(StrEnum):
    """Rule codes for composite episode id parsing violations."""

    MALFORMED_COMPOSITE_EPISODE_ID = "MALFORMED_COMPOSITE_EPISODE_ID"


class EpisodeCompositeId(CompoundValueObject):
    """Composite episode identifier used by the frontend.

    Attributes:
        series_id: Typed external series ID (``ser_xxx`` format).
        season_number: Season number.
        episode_number: Episode number within the season.

    Example:
        >>> from src.shared_kernel.value_objects.media_id import SeriesId
        >>> eid = EpisodeCompositeId.build(SeriesId("ser_Hy9VjMfILYZe"), 3, 2)
        >>> eid.media_id
        'epi_ser_Hy9VjMfILYZe_3_2'
        >>> EpisodeCompositeId.parse("epi_ser_Hy9VjMfILYZe_3_2").episode_number
        2
    """

    series_id: SeriesId
    season_number: int
    episode_number: int

    @property
    def media_id(self) -> str:
        """Build the composite media_id string."""
        prefix = self.media_id_prefix_for(self.series_id)
        return f"{prefix}{self.season_number}_{self.episode_number}"

    @classmethod
    def media_id_prefix_for(cls, series_id: SeriesId) -> str:
        """Return the media_id prefix shared by every episode of a series.

        Useful for prefix queries (e.g. soft-deleting every episode-progress
        row of a series) without rebuilding the wire format by hand.

        Args:
            series_id: The series whose episode ids share the prefix.

        Returns:
            The ``epi_{series_id}_`` prefix string.
        """
        return f"{_PREFIX}{series_id}_"

    @classmethod
    def build(
        cls, series_id: SeriesId, season_number: int, episode_number: int
    ) -> EpisodeCompositeId:
        """Create from individual components.

        Args:
            series_id: Typed external series ID.
            season_number: Season number.
            episode_number: Episode number.

        Returns:
            A new EpisodeCompositeId instance.
        """
        return cls(
            series_id=series_id,
            season_number=season_number,
            episode_number=episode_number,
        )

    @classmethod
    def parse(cls, media_id: str) -> EpisodeCompositeId | None:
        """Parse a composite media_id string.

        Distinguishes "this is not a composite episode key" from "this is a
        malformed one": only strings carrying the ``epi_ser_`` marker are
        treated as episode keys, so a plain ``epi_{base62}`` catalog id, a
        ``mov_xxx`` id or garbage yields ``None``, while a marker-bearing
        string with a broken structure or invalid series id raises.

        Args:
            media_id: The candidate composite media_id (e.g. ``epi_ser_XXX_S_E``).

        Returns:
            EpisodeCompositeId when the string is a well-formed composite
            episode key, or None when it is not an episode key at all.

        Raises:
            DomainValidationException: When the string carries the composite
                marker but its structure, numbers or series id are invalid.
        """
        if not media_id.startswith(_COMPOSITE_MARKER):
            return None

        # epi_ser_Hy9VjMfILYZe_3_2 → strip "epi_" → "ser_Hy9VjMfILYZe_3_2"
        rest = media_id[len(_PREFIX) :]
        parts = rest.rsplit("_", 2)
        if len(parts) != 3:
            raise cls._malformed(media_id)

        series_id_str, season_str, episode_str = parts
        try:
            season_number = int(season_str)
            episode_number = int(episode_str)
        except ValueError as exc:
            raise cls._malformed(media_id) from exc

        # Re-wrap an invalid series part so every malformed-but-marked id
        # surfaces under the same rule code instead of SeriesId's generic one.
        try:
            series_id = SeriesId(series_id_str)
        except DomainValidationException as exc:
            raise cls._malformed(media_id) from exc

        return cls.build(series_id, season_number, episode_number)

    @staticmethod
    def _malformed(media_id: str) -> DomainValidationException:
        """Build the uniform "malformed composite episode id" error."""
        return DomainValidationException(
            message=f"Malformed composite episode id: {media_id}",
            message_code=EpisodeCompositeIdRuleCodes.MALFORMED_COMPOSITE_EPISODE_ID,
            object_type="EpisodeCompositeId",
        )


__all__ = ["EpisodeCompositeId", "EpisodeCompositeIdRuleCodes"]
