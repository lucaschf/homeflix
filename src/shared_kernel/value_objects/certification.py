"""Certification — a rating label paired with the age it normalizes to (ADR-035)."""

from typing import Self

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.content_rating import ContentRating
from src.shared_kernel.value_objects.rating_system import RatingSystem


class Certification(CompoundValueObject):
    """A content rating in both the form it is shown and the form it is compared.

    Holds the three facts that have to travel together (ADR-035,
    decision 2): the scale the label belongs to, the label verbatim as
    the provider emitted it, and the minimum age it normalizes to.

    Keeping ``label`` untouched is what lets the badge in the UI keep
    displaying ``PG-13`` or ``A12`` while the catalog filters on
    ``minimum_age``. Keeping ``system`` is what makes the normalization
    revisable later: without it, an MPA ``PG`` from 1972 and one from
    2011 are the same three characters.

    Attributes:
        system: The scale ``label`` is written on.
        label: The certification exactly as the provider emitted it.
        minimum_age: The comparable age, or ``None`` when the label
            carries no determinable age (``NR``, ``UR``, or anything
            outside the known scales). ``None`` is *not* "suitable for
            everyone" — consumers resolve it through
            :meth:`AgeRating.allows`, which treats it as adult.

    Example:
        >>> from src.shared_kernel.value_objects import AgeRating, ContentRating
        >>> cert = Certification(
        ...     system=RatingSystem.BR_DEJUS,
        ...     label=ContentRating("12"),
        ...     minimum_age=AgeRating(12),
        ... )
        >>> cert.is_determined
        True
        >>> cert.label.value
        '12'
    """

    system: RatingSystem
    label: ContentRating
    minimum_age: AgeRating | None = None

    @property
    def is_determined(self) -> bool:
        """Whether this certification yields a comparable age."""
        return self.minimum_age is not None

    @classmethod
    def undetermined(cls, label: ContentRating, *, system: RatingSystem | None = None) -> Self:
        """Build a certification whose label is known but whose age is not.

        Args:
            label: The provider's label, preserved for display.
            system: The scale, when it could be identified despite the
                age being underivable. Defaults to
                :attr:`RatingSystem.UNKNOWN`.

        Returns:
            A certification with ``minimum_age`` unset.
        """
        return cls(system=system or RatingSystem.UNKNOWN, label=label, minimum_age=None)


__all__ = ["Certification"]
