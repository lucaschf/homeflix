"""Internal helper to project a Profile entity into a ProfileOutput DTO."""

from src.modules.identity.application.dtos.identity_dtos import ProfileOutput
from src.modules.identity.domain.entities.profile import Profile


def profile_to_output(profile: Profile) -> ProfileOutput:
    """Convert a domain ``Profile`` to a ``ProfileOutput`` DTO.

    Args:
        profile: A persisted profile (must have an ``id`` set).

    Returns:
        A frozen ``ProfileOutput`` with ISO-8601 timestamps.

    Raises:
        ValueError: If the profile has no id (not yet persisted).
    """
    if profile.id is None:
        raise ValueError("Cannot project a Profile without id to output")

    return ProfileOutput(
        id=profile.id.value,
        user_id=profile.user_id.value,
        name=profile.name.value,
        avatar_url=profile.avatar_url,
        is_kids=profile.is_kids,
        allowed_library_ids=list(profile.allowed_library_ids),
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat(),
    )


__all__ = ["profile_to_output"]
