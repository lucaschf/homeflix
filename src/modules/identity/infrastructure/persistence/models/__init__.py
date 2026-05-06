"""Identity SQLAlchemy ORM models.

Importing this module registers the models on the shared SQLAlchemy
metadata so alembic ``autogenerate`` and ``upgrade`` discover them.
"""

from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel

__all__ = ["AccessTokenModel", "ProfileModel", "UserModel"]
