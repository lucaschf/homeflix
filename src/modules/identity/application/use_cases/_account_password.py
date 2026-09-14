"""Internal helper: confirm the account password before a sensitive change."""

from src.modules.identity.application.errors import AccountPasswordInvalidError
from src.modules.identity.application.ports import PasswordHasherPort
from src.modules.identity.domain.entities.user import User


def ensure_account_password(
    user: User,
    password: str,
    password_hasher: PasswordHasherPort,
) -> None:
    """Raise unless ``password`` is the account's current password.

    A valid session is not enough to change the parental PIN: the account
    password is the root of trust above it (ADR-035, Amendment 7 D3). An
    account without a password hash cannot confirm anything, so it is
    refused rather than let through.

    Args:
        user: The account making the change.
        password: Plaintext password supplied with the request.
        password_hasher: Port that checks ``password`` against the stored hash.

    Raises:
        AccountPasswordInvalidError: If the password does not match, or the
            account has no password hash (HTTP 403, never 401).
    """
    if user.hashed_password is None or not password_hasher.verify(
        password,
        user.hashed_password,
    ):
        raise AccountPasswordInvalidError(message="The account password is incorrect")


__all__ = ["ensure_account_password"]
