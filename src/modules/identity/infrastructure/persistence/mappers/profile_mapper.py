"""Mapper between Profile domain entity and ProfileModel ORM model.

Profile rows have a UUID primary key (for consistency with the rest of
the identity BC) and a UUID FK ``user_id`` to ``users.id``. The domain
only sees prefixed ``ProfileId`` / ``UserId``. The repository is
responsible for resolving the user's UUID before calling
``to_model``/``update_model`` — the mapper itself never does the
lookup, keeping it dependency-free and synchronous.
"""

import uuid
from datetime import UTC, datetime

from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


def _ensure_utc(value: datetime | None) -> datetime | None:
    """Attach UTC tzinfo to naive datetimes loaded from the DB."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ProfileMapper:
    """Bidirectional mapper for ``Profile`` ↔ ``ProfileModel``."""

    @staticmethod
    def to_model(entity: Profile, user_uuid: uuid.UUID) -> ProfileModel:
        """Convert a Profile entity to a freshly-constructed ProfileModel.

        Args:
            entity: The Profile to persist (must have an id assigned).
            user_uuid: The internal UUID of the owning user, resolved
                by the repository via a SELECT on ``users.external_id``
                before calling this method.

        Returns:
            A new ``ProfileModel`` ready to be added to the session.

        Raises:
            ValueError: If the entity has no id.
        """
        if entity.id is None:
            raise ValueError("Cannot map Profile entity without ID to model")

        return ProfileModel(
            external_id=str(entity.id),
            user_id=user_uuid,
            name=entity.name.value,
            avatar_url=entity.avatar_url,
            is_kids=entity.is_kids,
        )

    @staticmethod
    def to_entity(model: ProfileModel, user_external_id: str) -> Profile:
        """Convert a ProfileModel back into a Profile domain entity.

        Args:
            model: The SQLAlchemy model loaded from the session.
            user_external_id: The owning user's external ID, resolved
                by the repository (typically via a JOIN) so the
                returned entity carries the prefixed ``UserId`` rather
                than a UUID.

        Returns:
            The reconstructed ``Profile`` with prefixed VO IDs.
        """
        return Profile(
            id=ProfileId(model.external_id),
            user_id=UserId(user_external_id),
            name=ProfileName(model.name),
            avatar_url=model.avatar_url,
            is_kids=model.is_kids,
            created_at=_ensure_utc(model.created_at) or datetime.now(UTC),
            updated_at=_ensure_utc(model.updated_at) or datetime.now(UTC),
        )

    @staticmethod
    def update_model(model: ProfileModel, entity: Profile) -> ProfileModel:
        """Apply mutable Profile fields to an existing model.

        ``user_id`` is intentionally NOT touched — transferring profile
        ownership is not a supported operation. The repository should
        not attempt to call ``update_model`` on a profile whose
        ``user_id`` differs from the existing model.

        Args:
            model: The existing model to mutate in place.
            entity: The domain entity carrying the new state.

        Returns:
            The same ``model`` reference, mutated.
        """
        model.name = entity.name.value
        model.avatar_url = entity.avatar_url
        model.is_kids = entity.is_kids
        return model


__all__ = ["ProfileMapper"]
