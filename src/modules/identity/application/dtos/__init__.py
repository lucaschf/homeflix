"""Identity application DTOs (use case Input/Output dataclasses)."""

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    DeleteProfileInput,
    ListProfilesForUserInput,
    ProfileOutput,
    SwitchProfileInput,
    UpdateProfileInput,
)

__all__ = [
    "CreateProfileInput",
    "DeleteProfileInput",
    "ListProfilesForUserInput",
    "ProfileOutput",
    "SwitchProfileInput",
    "UpdateProfileInput",
]
