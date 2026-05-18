"""Identity application DTOs (use case Input/Output dataclasses)."""

from src.modules.identity.application.dtos.identity_dtos import (
    CreateAdminUserInput,
    CreateProfileInput,
    DeleteAdminUserInput,
    DeleteProfileInput,
    GetUserDetailInput,
    ListProfilesForUserInput,
    ListUsersInput,
    ProfileOutput,
    SwitchProfileInput,
    UpdateProfileInput,
    UpdateUserRoleInput,
    UserDetail,
    UserSummary,
)

__all__ = [
    "CreateAdminUserInput",
    "CreateProfileInput",
    "DeleteAdminUserInput",
    "DeleteProfileInput",
    "GetUserDetailInput",
    "ListProfilesForUserInput",
    "ListUsersInput",
    "ProfileOutput",
    "SwitchProfileInput",
    "UpdateProfileInput",
    "UpdateUserRoleInput",
    "UserDetail",
    "UserSummary",
]
