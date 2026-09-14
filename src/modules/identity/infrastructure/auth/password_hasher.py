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

    def verify(self, plain: str, hashed: str) -> bool:
        """Check ``plain`` against ``hashed`` with ``PasswordHelper.verify_and_update``.

        The helper also returns a replacement hash when ``hashed`` uses
        deprecated parameters. It is discarded on purpose: this port only
        verifies, and a caller that stored it would be writing a column
        (the account password, or the parental PIN) as a side effect of a
        read. FastAPI Users still upgrades the account password on login.
        """
        verified, _discarded_rehash = self._helper.verify_and_update(plain, hashed)
        return verified


__all__ = ["FastApiUsersPasswordHasher"]
