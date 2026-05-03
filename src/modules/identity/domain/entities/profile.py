"""Profile aggregate root."""

from __future__ import annotations

from typing import Self

from pydantic import Field

from src.building_blocks.domain.entity import AggregateRoot
from src.modules.identity.domain.value_objects.profile_id import ProfileId
from src.modules.identity.domain.value_objects.profile_name import (  # noqa: TCH001
    ProfileName,
)
from src.modules.identity.domain.value_objects.user_id import UserId  # noqa: TCH001


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
        is_kids: Marks the profile as kids-mode (used by the future
            library ACL — see ADR-010 PR 6).

    Example:
        >>> profile = Profile.create(
        ...     user_id=UserId("usr_2xK9mPqR7nL4"),
        ...     name=ProfileName("Lucas"),
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

    @classmethod
    def create(
        cls,
        user_id: UserId,
        name: ProfileName,
        *,
        is_kids: bool = False,
        avatar_url: str | None = None,
    ) -> Profile:
        """Build a fresh ``Profile`` (id assigned at persistence time)."""
        return cls(
            user_id=user_id,
            name=name,
            is_kids=is_kids,
            avatar_url=avatar_url,
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


__all__ = ["Profile"]
