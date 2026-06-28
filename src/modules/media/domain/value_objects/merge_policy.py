"""Policy for reconciling provider metadata with stored entity values."""

from enum import StrEnum


class MergePolicy(StrEnum):
    """How an enrichment pass reconciles provider data with stored values.

    ``FILL_IF_EMPTY``: routine re-enrich — only write a field the entity
    left empty, protecting prior user/enrich edits.
    ``OVERWRITE``: relink / forced refresh — replace stored values with the
    newly-matched provider data.

    Example:
        >>> MergePolicy.FILL_IF_EMPTY.should_write("kept")
        False
        >>> MergePolicy.OVERWRITE.should_write("replaced")
        True
    """

    FILL_IF_EMPTY = "fill_if_empty"
    OVERWRITE = "overwrite"

    @classmethod
    def from_force(cls, force: bool) -> "MergePolicy":
        """Bridge the public ``force`` flag (``EnrichMediaInput``) to a policy."""
        return cls.OVERWRITE if force else cls.FILL_IF_EMPTY

    def should_write(self, current: object) -> bool:
        """Return ``True`` when a provider value should be written over *current*.

        Always under ``OVERWRITE``; only when *current* is empty/falsy under
        ``FILL_IF_EMPTY``. Replaces the old ``(force or not current)`` guard.
        """
        return self is MergePolicy.OVERWRITE or not current

    @property
    def overwrites(self) -> bool:
        """Whether stored values are replaced regardless of emptiness.

        For the custom guards that aren't plain fill-if-empty (clearing a
        stale field, replacing a placeholder/combined title, replace-vs-merge
        of localized overrides), so they read in intent terms and keep all
        policy semantics on the value object.
        """
        return self is MergePolicy.OVERWRITE


__all__ = ["MergePolicy"]
