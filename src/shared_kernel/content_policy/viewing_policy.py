"""What a profile may see — the definition the catalog query projects (ADR-035)."""

from typing import TYPE_CHECKING, Self

from pydantic import field_validator

if TYPE_CHECKING:
    from collections.abc import Sequence

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.library_id import LibraryId


class ViewingPolicy(CompoundValueObject):
    """The two axes that decide whether a profile may see a title.

    This class is the **definition** of catalog visibility; the
    ``WHERE`` clause a repository builds is a *projection* of it
    (ADR-017). An integration test holds the two to each other, so the
    rule cannot drift into SQL and become unreadable, and
    :meth:`permits` cannot decay into an ornament while the query
    decides something subtly different.

    The axes compose by AND — a denial on either wins:

    - ``allowed_library_ids`` answers "does this profile reach this
      *shelf*?". Structural and rarely changed.
    - ``maturity_limit`` answers "may this profile see this *title*?".
      The day-to-day axis, applied across every library at once, which
      is what removes the need for a separate kids library.

    Attributes:
        allowed_library_ids: Libraries this profile may read.
            **Empty means deny-all**, not "all allowed" — the profile's
            stored ACL is the source of truth and its decode is
            fail-closed (ADR-018 §3). Raw strings are converted and
            validated on assignment, so a malformed id fails at
            construction instead of silently becoming a denial.
        maturity_limit: Highest age this profile may watch up to, or
            ``None`` for unrestricted. ``None`` is the default because
            it is the behavior of every profile that predates the
            feature.

    Example:
        >>> from src.shared_kernel.value_objects import AgeRating
        >>> policy = ViewingPolicy(
        ...     allowed_library_ids=["lib_movies123456"],
        ...     maturity_limit=AgeRating(12),
        ... )
        >>> policy.permits(
        ...     library_id=LibraryId("lib_movies123456"),
        ...     minimum_age=AgeRating(10),
        ... )
        True
        >>> policy.permits(
        ...     library_id=LibraryId("lib_movies123456"),
        ...     minimum_age=None,          # unclassified title
        ... )
        False
    """

    allowed_library_ids: tuple[LibraryId, ...] = ()
    maturity_limit: AgeRating | None = None

    @field_validator("allowed_library_ids", mode="before")
    @classmethod
    def convert_allowed_library_ids(
        cls, v: "Sequence[str | LibraryId] | None"
    ) -> tuple[LibraryId, ...]:
        """Convert raw strings to ``LibraryId``, validating the format."""
        if v is None:
            return ()
        return tuple(item if isinstance(item, LibraryId) else LibraryId(item) for item in v)

    @classmethod
    def unrestricted(cls, allowed_library_ids: "Sequence[str | LibraryId]") -> Self:
        """Build a policy that restricts by library only.

        Args:
            allowed_library_ids: The profile's library ACL.

        Returns:
            A policy with no maturity limit.
        """
        return cls(allowed_library_ids=allowed_library_ids, maturity_limit=None)

    @property
    def denies_everything(self) -> bool:
        """Whether this policy can never permit anything.

        True when the library ACL is empty. Callers use it to skip the
        query entirely and return an empty page.
        """
        return not self.allowed_library_ids

    @property
    def restricts_maturity(self) -> bool:
        """Whether an age limit applies at all."""
        return self.maturity_limit is not None

    def permits_library(self, library_id: LibraryId) -> bool:
        """Whether the library axis alone allows this title."""
        return library_id in self.allowed_library_ids

    def permits_maturity(self, minimum_age: "AgeRating | None") -> bool:
        """Whether the age axis alone allows this title.

        An unrestricted policy permits everything, including titles
        with no determinable age. A limited one defers to
        :meth:`AgeRating.allows`, which resolves the undetermined case
        to adult.
        """
        if self.maturity_limit is None:
            return True
        return self.maturity_limit.allows(minimum_age)

    def permits(self, *, library_id: LibraryId, minimum_age: "AgeRating | None") -> bool:
        """Whether this profile may see a title with these properties.

        Args:
            library_id: The library the title belongs to.
            minimum_age: The title's normalized minimum age, or
                ``None`` when it carries no determinable certification.

        Returns:
            ``True`` only when both axes allow it.
        """
        return self.permits_library(library_id) and self.permits_maturity(minimum_age)


__all__ = ["ViewingPolicy"]
