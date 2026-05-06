"""Profile aggregate root."""

from __future__ import annotations

from typing import Self

from pydantic import Field

from src.building_blocks.domain.entity import AggregateRoot
from src.modules.identity.domain.value_objects.profile_name import (  # noqa: TCH001
    ProfileName,
)
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
            creation (renaming a profile or changing kids flag uses
            the ``with_*`` helpers; transferring ownership is not a
            supported operation).
        name: Display name shown in the profile picker.
        avatar_url: Optional URL to an avatar image.
        is_kids: Marks the profile as kids-mode. Independent of the
            ACL list — the kids flag is a UX hint; the ACL is the
            actual authorization gate.
        allowed_library_ids: Library external ids (``lib_xxx``) this
            profile is allowed to see in the catalog. Default-deny:
            an empty list means the profile sees nothing. The catalog
            filter (see PR 6c) is a no-op when this list is empty
            beyond returning empty pages — the field is the source
            of truth, not a hint.

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
    is_kids: bool = False
    allowed_library_ids: list[str] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        user_id: UserId,
        name: ProfileName,
        *,
        is_kids: bool = False,
        avatar_url: str | None = None,
        allowed_library_ids: list[str] | None = None,
    ) -> Profile:
        """Build a fresh ``Profile`` (id assigned at persistence time)."""
        return cls(
            user_id=user_id,
            name=name,
            is_kids=is_kids,
            avatar_url=avatar_url,
            allowed_library_ids=list(allowed_library_ids) if allowed_library_ids else [],
        )

    def with_name(self, name: ProfileName) -> Self:
        """Return a copy with the given name."""
        return self.with_updates(name=name)

    def with_kids_flag(self, *, is_kids: bool) -> Self:
        """Return a copy with the kids flag toggled."""
        return self.with_updates(is_kids=is_kids)

    def with_avatar(self, avatar_url: str | None) -> Self:
        """Return a copy with the given avatar URL (or ``None`` to clear)."""
        return self.with_updates(avatar_url=avatar_url)

    def with_allowed_library_ids(self, library_ids: list[str]) -> Self:
        """Return a copy whose ACL is replaced by ``library_ids``.

        Replaces the list entirely — there is no partial-add or
        partial-remove operation. Callers that want to grant access
        compute the new list themselves and pass the full set, which
        keeps the aggregate's invariants explicit at one update site.
        """
        return self.with_updates(allowed_library_ids=list(library_ids))


__all__ = ["Profile"]
