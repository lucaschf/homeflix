"""FastAPI Users ``UserManager`` for the identity bounded context.

``UserManager`` is FastAPI Users' extension point for password reset,
verification, registration hooks, and per-request user-DB plumbing.
For PR 1 we only need the minimum: a UUID-typed manager subclass that
wires the configured ``secret_key`` for token signing. The
registration / verification / reset flows are NOT exposed in PR 1
(no public ``/auth/register`` route — admins are bootstrapped via a
CLI script in slice 6), so the lifecycle hooks (``on_after_register``
etc.) are deliberately left at their no-op defaults.
"""

import uuid

from fastapi_users import BaseUserManager, UUIDIDMixin

from src.config.settings import get_settings
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel


class UserManager(UUIDIDMixin, BaseUserManager[UserModel, uuid.UUID]):
    """Identity user manager.

    ``reset_password_token_secret`` and ``verification_token_secret``
    are read from settings at instantiation; both flows are inactive
    in PR 1 but the values are wired so future PRs can mount the
    routers without touching this class.
    """

    @property
    def reset_password_token_secret(self) -> str:  # type: ignore[override]
        """Secret used to sign password-reset tokens."""
        return get_settings().secret_key.get_secret_value()

    @property
    def verification_token_secret(self) -> str:  # type: ignore[override]
        """Secret used to sign email-verification tokens."""
        return get_settings().secret_key.get_secret_value()


__all__ = ["UserManager"]
