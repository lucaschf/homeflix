"""Unit tests for the FastAPI Users-backed ``PasswordHasherPort`` adapter.

Runs the real ``PasswordHelper`` (Argon2): a fake would prove nothing
about whether verification actually checks the credential.
"""

import pytest

from src.modules.identity.infrastructure.auth.password_hasher import (
    FastApiUsersPasswordHasher,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def hasher() -> FastApiUsersPasswordHasher:
    return FastApiUsersPasswordHasher()


@pytest.fixture(scope="module")
def pin_hash(hasher: FastApiUsersPasswordHasher) -> str:
    return hasher.hash("904518")


class TestFastApiUsersPasswordHasher:
    def test_hash_should_not_store_the_plaintext(self, pin_hash: str) -> None:
        assert pin_hash != "904518"
        assert "904518" not in pin_hash

    def test_verify_should_accept_the_hashed_credential(
        self, hasher: FastApiUsersPasswordHasher, pin_hash: str
    ) -> None:
        assert hasher.verify("904518", pin_hash) is True

    @pytest.mark.parametrize("other", ["904519", "000000", ""])
    def test_verify_should_reject_any_other_credential(
        self, hasher: FastApiUsersPasswordHasher, pin_hash: str, other: str
    ) -> None:
        assert hasher.verify(other, pin_hash) is False
