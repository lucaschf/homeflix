"""Port for hashing user passwords.

Authentication today runs through FastAPI Users (the dependency
owns the ``hashed_password`` column on its own row), but the admin
"create user" use case needs to set an initial hashed password
*before* the user logs in for the first time. Going through this
port keeps the use case free of any direct FastAPI Users import —
the adapter wraps ``fastapi_users.password.PasswordHelper`` and the
domain only ever sees opaque hashed strings.

Swapping for argon2 (or any other hasher) is then a single adapter
change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PasswordHasherPort(ABC):
    """Produce a hashed-password string from a plaintext credential."""

    @abstractmethod
    def hash(self, password: str) -> str:
        """Return the storage-ready hash for ``password``.

        The plaintext input is never persisted — callers should drop
        it from their scope as soon as the hash is in hand.

        Args:
            password: Plaintext password chosen by the admin.

        Returns:
            Hashed representation suitable for
            ``UserModel.hashed_password`` (BCrypt today).
        """
        ...


__all__ = ["PasswordHasherPort"]
