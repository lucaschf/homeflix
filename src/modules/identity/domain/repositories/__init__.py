"""Identity domain repository interfaces."""

from src.modules.identity.domain.repositories.access_token_repository import (
    AccessTokenRepository,
    AccessTokenSnapshot,
)
from src.modules.identity.domain.repositories.profile_repository import (
    ProfileRepository,
)
from src.modules.identity.domain.repositories.user_repository import UserRepository

__all__ = [
    "AccessTokenRepository",
    "AccessTokenSnapshot",
    "ProfileRepository",
    "UserRepository",
]
