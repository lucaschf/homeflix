"""Shared helper for composite episode media IDs.

The frontend identifies episodes using composite keys in the format
``epi_{series_id}_{season_number}_{episode_number}`` (e.g.
``epi_ser_Hy9VjMfILYZe_3_2``). This module provides build/parse
utilities so the format is defined in a single place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EpisodeCompositeId:
    """Composite episode identifier used by the frontend.

    Attributes:
        series_id: External series ID (``ser_xxx`` format).
        season_number: Season number.
        episode_number: Episode number within the season.

    Example:
        >>> eid = EpisodeCompositeId.build("ser_Hy9VjMfILYZe", 3, 2)
        >>> eid.media_id
        'epi_ser_Hy9VjMfILYZe_3_2'
        >>> EpisodeCompositeId.parse("epi_ser_Hy9VjMfILYZe_3_2")
        EpisodeCompositeId(series_id='ser_Hy9VjMfILYZe', season_number=3, episode_number=2)
    """

    series_id: str
    season_number: int
    episode_number: int

    @property
    def media_id(self) -> str:
        """Build the composite media_id string."""
        return f"epi_{self.series_id}_{self.season_number}_{self.episode_number}"

    @classmethod
    def build(cls, series_id: str, season_number: int, episode_number: int) -> EpisodeCompositeId:
        """Create from individual components.

        Args:
            series_id: External series ID.
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

        Args:
            media_id: The composite media_id (e.g. ``epi_ser_XXX_S_E``).

        Returns:
            EpisodeCompositeId if valid, None otherwise.
        """
        if not media_id.startswith("epi_ser_"):
            return None
        # epi_ser_Hy9VjMfILYZe_3_2 → strip "epi_" → "ser_Hy9VjMfILYZe_3_2"
        rest = media_id[4:]
        parts = rest.rsplit("_", 2)
        if len(parts) != 3:
            return None
        series_id_str, season_str, episode_str = parts
        try:
            return cls(
                series_id=series_id_str,
                season_number=int(season_str),
                episode_number=int(episode_str),
            )
        except ValueError:
            return None


__all__ = ["EpisodeCompositeId"]
