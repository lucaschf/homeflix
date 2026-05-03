"""Identity domain value objects."""

from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.profile_id import ProfileId
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.domain.value_objects.user_id import UserId
from src.modules.identity.domain.value_objects.user_role import UserRole

__all__ = ["Email", "ProfileId", "ProfileName", "UserId", "UserRole"]
