"""FastAPI Users-backed ``PasswordHasherPort`` adapter."""

from fastapi_users.password import PasswordHelper

from src.modules.identity.application.ports import PasswordHasherPort


class FastApiUsersPasswordHasher(PasswordHasherPort):
    """Adapter delegating to FastAPI Users' ``PasswordHelper``.

    Single shared instance is fine — ``PasswordHelper`` is
    stateless once constructed. Kept inside the auth namespace
    because the FastAPI Users dependency already lives there; if
    we ever swap hashers we only need to change this adapter.
    """

    def __init__(self) -> None:
        self._helper = PasswordHelper()

    def hash(self, password: str) -> str:
        """Return the BCrypt hash backing ``password``."""
        return self._helper.hash(password)


__all__ = ["FastApiUsersPasswordHasher"]
