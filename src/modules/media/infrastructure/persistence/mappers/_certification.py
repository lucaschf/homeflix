"""Certification ↔ three columns, shared by the movie and series mappers.

``Certification`` is one value object but three columns, because each
part is read on its own: the catalog filters on ``minimum_age`` in SQL,
the UI renders ``content_rating``, and ``rating_system`` is what makes
the normalization revisable later (ADR-035). Packing them into JSON
would put the filter column inside a blob.
"""

from typing import Protocol

from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.certification import Certification
from src.shared_kernel.value_objects.content_rating import ContentRating
from src.shared_kernel.value_objects.rating_system import RatingSystem


class _CertificationColumns(Protocol):
    """The three columns every classifiable catalog model carries."""

    content_rating: str | None
    minimum_age: int | None
    rating_system: str | None


def certification_to_columns(
    certification: Certification | None,
) -> tuple[str | None, int | None, str | None]:
    """Flatten a certification into ``(label, minimum_age, system)``."""
    if certification is None:
        return None, None, None
    return (
        certification.label.value,
        certification.minimum_age.value if certification.minimum_age else None,
        certification.system.value,
    )


def certification_from_columns(model: _CertificationColumns) -> Certification | None:
    """Rebuild a certification from a row, or ``None`` when unlabelled.

    The label is what makes a certification exist: a row with an age but
    no label is not a certification, it is corruption, and reading it as
    ``None`` keeps the title out of every limited profile rather than
    inventing a label for it.

    An unrecognized ``rating_system`` string — a value written by a
    newer revision, or hand-edited — degrades to
    :attr:`RatingSystem.UNKNOWN` instead of raising, because a mapper
    that throws takes the whole catalog page down with it. The age still
    comes through, so filtering keeps working.
    """
    if not model.content_rating:
        return None

    try:
        system = RatingSystem(model.rating_system) if model.rating_system else RatingSystem.UNKNOWN
    except ValueError:
        system = RatingSystem.UNKNOWN

    return Certification(
        system=system,
        label=ContentRating(model.content_rating),
        minimum_age=AgeRating(model.minimum_age) if model.minimum_age is not None else None,
    )


__all__ = ["certification_from_columns", "certification_to_columns"]
