"""Identity use cases."""

from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.delete_profile import (
    DeleteProfileUseCase,
)
from src.modules.identity.application.use_cases.delete_profile_avatar import (
    DeleteProfileAvatarUseCase,
)
from src.modules.identity.application.use_cases.list_profiles_for_user import (
    ListProfilesForUserUseCase,
)
from src.modules.identity.application.use_cases.switch_profile import (
    SwitchProfileUseCase,
)
from src.modules.identity.application.use_cases.update_profile import (
    UpdateProfileUseCase,
)
from src.modules.identity.application.use_cases.upload_profile_avatar import (
    UploadProfileAvatarUseCase,
)

__all__ = [
    "CreateProfileUseCase",
    "DeleteProfileAvatarUseCase",
    "DeleteProfileUseCase",
    "ListProfilesForUserUseCase",
    "SwitchProfileUseCase",
    "UpdateProfileUseCase",
    "UploadProfileAvatarUseCase",
]
