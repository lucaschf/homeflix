"""Profile aggregate root."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from pydantic import Field, field_validator

if TYPE_CHECKING:
    from collections.abc import Sequence

from src.building_blocks.domain.entity import AggregateRoot
from src.modules.identity.domain.value_objects.profile_name import (  # noqa: TCH001
    ProfileName,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.age_rating import AgeRating  # noqa: TCH001
from src.shared_kernel.value_objects.library_id import LibraryId
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId  # noqa: TCH001


class Profile(AggregateRoot[ProfileId]):
    """Personalization profile owned by a ``User``.

    Modeled as a separate aggregate root (not a child entity inside
    ``User``) so authentication checks — which run on every request —
    do not pay the cost of hydrating the profile list. Cross-BC
    consumers (``watch_progress``, ``collections``, ``preferences``)
    reference only ``ProfileId``. Ownership is enforced as an
    invariant at the use-case boundary: every operation that mutates
    a profile validates ``profile.user_id == caller.id`` before
    proceeding. See ADR-010.

    Attributes:
        id: External profile ID (``prf_xxx``). Database stores a UUID.
        user_id: Owner's external ID. Required and immutable after
            creation (renaming a profile or changing its maturity limit
            uses the ``with_*`` helpers; transferring ownership is not
            a supported operation).
        name: Display name shown in the profile picker.
        avatar_url: Optional URL to an avatar image.
        maturity_limit: Highest minimum age this profile may watch, or
            ``None`` for unrestricted (ADR-035). Every profile that
            predates the feature has ``None``. The kids flag is no
            longer stored: :attr:`is_kids` is derived from this limit.
        allowed_library_ids: Typed ``LibraryId`` ACL (``lib_xxx``) of
            the libraries this profile may see in the catalog. Raw
            strings are converted (and validated) on assignment, so a
            malformed id fails at write time instead of becoming a
            silent default-deny (ADR-018). Default-deny: an empty
            list means the profile sees nothing. The catalog filter
            (see PR 6c) is a no-op when this list is empty beyond
            returning empty pages — the field is the source of truth,
            not a hint.

    Example:
        >>> profile = Profile.create(
        ...     user_id=UserId("usr_2xK9mPqR7nL4"),
        ...     name=ProfileName("Lucas"),
        ...     allowed_library_ids=["lib_movies12345"],
        ... )
        >>> renamed = profile.with_name(ProfileName("Luc"))
        >>> renamed.name.value
        'Luc'
    """

    id: ProfileId | None = Field(default=None)
    user_id: UserId
    name: ProfileName
    avatar_url: str | None = None
    maturity_limit: AgeRating | None = None
    allowed_library_ids: list[LibraryId] = Field(default_factory=list)

    @field_validator("allowed_library_ids", mode="before")
    @classmethod
    def convert_allowed_library_ids(cls, v: Sequence[str | LibraryId] | None) -> list[LibraryId]:
        """Convert raw strings to ``LibraryId``, validating the format."""
        if v is None:
            return []
        return [item if isinstance(item, LibraryId) else LibraryId(item) for item in v]

    @property
    def is_kids(self) -> bool:
        """Whether this profile reads as a kids profile.

        Derived from :attr:`maturity_limit` (ADR-035) rather than
        stored, so there is no second write path that could disagree
        with the limit. A plain ``@property`` on purpose: a computed
        field would enter ``model_dump()`` and break every ``with_*``
        helper, which re-validates the dump under ``extra="forbid"``.

        Returns:
            ``True`` when a limit of 12 or lower applies; ``False`` for
            an unrestricted profile or a higher limit.
        """
        return self.maturity_limit is not None and self.maturity_limit.value <= 12

    @classmethod
    def create(
        cls,
        user_id: UserId,
        name: ProfileName,
        *,
        avatar_url: str | None = None,
        allowed_library_ids: Sequence[str | LibraryId] | None = None,
    ) -> Profile:
        """Build a fresh ``Profile`` (id assigned at persistence time)."""
        return cls(
            user_id=user_id,
            name=name,
            avatar_url=avatar_url,
            allowed_library_ids=list(allowed_library_ids) if allowed_library_ids else [],
        )

    def with_name(self, name: ProfileName) -> Self:
        """Return a copy with the given name."""
        return self.with_updates(name=name)

    def with_maturity_limit(self, limit: AgeRating | None) -> Self:
        """Return a copy with the given maturity limit.

        Args:
            limit: The highest minimum age the profile may watch, or
                ``None`` to make it unrestricted.

        Returns:
            A new profile carrying ``limit``.
        """
        return self.with_updates(maturity_limit=limit)

    def with_avatar(self, avatar_url: str | None) -> Self:
        """Return a copy with the given avatar URL (or ``None`` to clear)."""
        return self.with_updates(avatar_url=avatar_url)

    def with_allowed_library_ids(self, library_ids: Sequence[str | LibraryId]) -> Self:
        """Return a copy whose ACL is replaced by ``library_ids``.

        Replaces the list entirely — there is no partial-add or
        partial-remove operation. Callers that want to grant access
        compute the new list themselves and pass the full set, which
        keeps the aggregate's invariants explicit at one update site.
        """
        return self.with_updates(allowed_library_ids=list(library_ids))

    def viewing_policy(self) -> ViewingPolicy:
        """Return the policy that decides what this profile may see.

        The single place where a profile's fields become a
        ``ViewingPolicy``. Every BC's ``ProfileViewingPolicyAdapter``
        calls this instead of assembling the policy itself, so a new
        visibility axis (the maturity limit, ADR-035 §4) is wired here
        once rather than remembered in each adapter copy. An
        architecture test holds the adapters to it.

        Returns:
            A policy carrying this profile's library ACL and maturity
            limit. An empty ACL yields a deny-all policy (ADR-035 §5);
            a ``None`` limit leaves the age axis unrestricted.
        """
        return ViewingPolicy(
            allowed_library_ids=self.allowed_library_ids,
            maturity_limit=self.maturity_limit,
        )


__all__ = ["Profile"]
