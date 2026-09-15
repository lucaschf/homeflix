"""Mapper between Profile domain entity and ProfileModel ORM model.

Profile rows have a UUID primary key (for consistency with the rest of
the identity BC) and a UUID FK ``user_id`` to ``users.id``. The domain
only sees prefixed ``ProfileId`` / ``UserId``. The repository is
responsible for resolving the user's UUID before calling
``to_model`` — the mapper itself never does the lookup, keeping it
dependency-free and synchronous.
"""

import json
import uuid
from datetime import UTC, datetime

from src.building_blocks.domain.errors import DomainValidationException
from src.config.logging import get_logger
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.library_id import LibraryId
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

_logger = get_logger()


def _ensure_utc(value: datetime | None) -> datetime | None:
    """Attach UTC tzinfo to naive datetimes loaded from the DB."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _decode_allowed_libraries(profile_external_id: str, raw: str | None) -> list[LibraryId]:
    """Decode the JSON-encoded allowed_library_ids column into ``LibraryId``s.

    A null or unparsable value is coerced to an empty list so a bad
    row can never silently grant access — but the coercion is logged
    at WARNING so corrupted ACLs are observable in dashboards rather
    than disappearing into a silent default-deny.

    Individual entries that fail ``LibraryId`` validation are dropped
    with the same WARNING treatment (default-deny per entry, ADR-018):
    a corrupted entry must neither grant access nor make the whole
    profile unreadable.
    """
    if raw is None:
        return []
    if raw == "":
        return []
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        _logger.warning(
            "[identity] Malformed allowed_library_ids JSON; coercing to empty list",
            profile_external_id=profile_external_id,
            raw=raw,
        )
        return []
    if not isinstance(decoded, list):
        _logger.warning(
            "[identity] allowed_library_ids decoded to non-list; coercing to empty list",
            profile_external_id=profile_external_id,
            decoded_type=type(decoded).__name__,
        )
        return []
    valid: list[LibraryId] = []
    for item in decoded:
        try:
            valid.append(LibraryId(str(item)))
        except DomainValidationException:
            _logger.warning(
                "[identity] Invalid library id in allowed_library_ids; dropping entry",
                profile_external_id=profile_external_id,
                entry=item,
            )
    return valid


def _decode_maturity_limit(profile_external_id: str, raw: int | None) -> AgeRating | None:
    """Decode the ``maturity_limit`` column into an ``AgeRating``.

    NULL is the only value that means unrestricted. Anything else that
    is not a whole number within the scale — out of range, a float, a
    string — resolves to ``AgeRating(0)``, the most restrictive limit,
    and is logged at WARNING. Mapping a corrupted value to ``None``
    would silently lift every restriction on the profile, so the decode
    fails closed, like :func:`_decode_allowed_libraries`.

    Args:
        profile_external_id: The profile's external ID, for the log.
        raw: The value loaded from the column. Typed as the column is
            mapped, but SQLite does not enforce column types, so the
            decode does not trust the annotation.

    Returns:
        ``None`` for NULL, the decoded limit for a valid value, or
        ``AgeRating(0)`` for anything else.
    """
    if raw is None:
        return None
    try:
        return AgeRating(raw)
    except DomainValidationException:
        _logger.warning(
            "[identity] Invalid maturity_limit; coercing to the most restrictive limit",
            profile_external_id=profile_external_id,
            raw=raw,
        )
        return AgeRating(AgeRating.MIN)


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
            maturity_limit=None if entity.maturity_limit is None else entity.maturity_limit.value,
            allowed_library_ids=json.dumps(
                [library_id.value for library_id in entity.allowed_library_ids]
            ),
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
            maturity_limit=_decode_maturity_limit(model.external_id, model.maturity_limit),
            allowed_library_ids=_decode_allowed_libraries(
                model.external_id, model.allowed_library_ids
            ),
            created_at=_ensure_utc(model.created_at) or datetime.now(UTC),
            updated_at=_ensure_utc(model.updated_at) or datetime.now(UTC),
        )

    @staticmethod
    def update_values(entity: Profile) -> dict[str, str | None]:
        """Return the columns an update of an existing profile writes, as stored.

        The repository writes them with one conditional ``UPDATE`` rather
        than onto a loaded model, so the write can require the row to be
        live (``SqlAlchemyProfileRepository.save``).

        ``user_id`` is intentionally NOT among them — transferring profile
        ownership is not a supported operation.

        Neither are ``maturity_limit`` and the ``is_kids`` flag derived
        from it: ``SqlAlchemyProfileRepository.set_maturity_limit`` is their
        only writer on an existing profile. The entity may have been read
        before a concurrent limit change, and writing its limit here would
        write the old one back (ADR-035).

        Args:
            entity: The domain entity carrying the new state.

        Returns:
            ``name``, ``avatar_url`` and ``allowed_library_ids``, keyed by
            column name.
        """
        return {
            "name": entity.name.value,
            "avatar_url": entity.avatar_url,
            "allowed_library_ids": json.dumps(
                [library_id.value for library_id in entity.allowed_library_ids]
            ),
        }


__all__ = ["ProfileMapper"]
