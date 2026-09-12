"""Minimum-age value object — the comparable form of a content rating (ADR-035)."""

from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain import IntValueObject


class AgeRating(IntValueObject):
    """A minimum age, in years, on a comparable scale (ADR-035).

    The normalized form of a content rating: every certification label
    a provider emits (``L``, ``PG-13``, ``TV-MA``, ``16``) collapses to
    one of these so the catalog can answer "is this above or below that
    profile's limit?" — something ``ContentRating``, a free-form string,
    cannot answer.

    Used in two roles that share the scale but not the meaning:

    - on a title, the **minimum age required** to watch it;
    - on a profile, the **maturity limit** the viewer is allowed up to.

    :meth:`allows` reads in the profile direction and carries the
    fail-closed rule for unclassified content: a title whose age could
    not be determined requires :attr:`ADULT`, never zero. Mapping the
    unknown to zero is the silent failure this whole mechanism exists
    to avoid (ADR-035, decision 3).

    Comparison operators come from :class:`IntValueObject` and are
    deliberately not reimplemented here.

    Attributes:
        MIN: Lowest representable age (0 — suitable for all audiences).
        MAX: Highest representable age. 21 rather than 18 so scales
            that go past the adult threshold round-trip unchanged.
        ADULT: The age an undetermined rating resolves to.

    Example:
        >>> AgeRating(12) < AgeRating(14)
        True
        >>> AgeRating(12).allows(AgeRating(10))
        True
        >>> AgeRating(12).allows(None)       # unclassified title
        False
        >>> AgeRating(18).allows(None)
        True
    """

    MIN: ClassVar[int] = 0
    MAX: ClassVar[int] = 21
    ADULT: ClassVar[int] = 18

    # Inlined rather than pulled from a module-level enum, matching
    # LanguageCode / LanguageTag — the shared kernel owns its own codes
    # instead of depending on a context's rule-code table.
    _RULE_CODE: ClassVar[str] = "SHARED.AGE_RATING.OUT_OF_RANGE"

    @model_validator(mode="before")
    @classmethod
    def validate_age_range(cls, value: int) -> int:
        """Validate that the age is a whole number within the scale.

        Args:
            value: The age in years.

        Returns:
            The validated age.

        Raises:
            ValueError: If the value is not an integer or falls outside
                ``MIN..MAX``.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            # Defensive guard against programmer error; a limit submitted
            # through the API is coerced to int before reaching here. No
            # rule code — i18n only covers content-level violations
            # (matches ProfileName and LibraryName).
            raise ValueError("Age rating must be an integer")

        if value < cls.MIN:
            raise ValueError(f"Age rating cannot be negative (got {value}) [{cls._RULE_CODE}]")

        if value > cls.MAX:
            raise ValueError(f"Age rating cannot exceed {cls.MAX} (got {value}) [{cls._RULE_CODE}]")

        return value

    @classmethod
    def adult(cls) -> "AgeRating":
        """Return the age an undetermined rating resolves to."""
        return cls(cls.ADULT)

    def allows(self, required: "AgeRating | None") -> bool:
        """Whether a viewer limited to this age may watch such a title.

        Read on a profile's ``maturity_limit``. ``required`` is the
        title's minimum age, or ``None`` when the title carries no
        normalizable certification — which resolves to :attr:`ADULT`,
        so unclassified content stays hidden from every limited
        profile and visible only to unrestricted ones.

        Args:
            required: Minimum age the title demands, or ``None`` when
                undetermined.

        Returns:
            ``True`` when the title is within this limit.

        Example:
            >>> AgeRating(14).allows(AgeRating(14))
            True
            >>> AgeRating(14).allows(AgeRating(16))
            False
        """
        effective = self.ADULT if required is None else required.value
        return effective <= self.value


__all__ = ["AgeRating"]
