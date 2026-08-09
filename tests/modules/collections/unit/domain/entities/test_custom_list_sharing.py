"""Tests for CustomList share/unshare transitions."""

import pytest

from src.modules.collections.domain.entities import CustomList
from src.modules.collections.domain.value_objects import ShareToken
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


def _list() -> CustomList:
    return CustomList.create(profile_id=_PROFILE_ID, name="Mine", existing_count=0)


@pytest.mark.unit
class TestCustomListSharing:
    """The is_shared flag and shared()/unshared() transitions."""

    def test_new_list_is_not_shared(self) -> None:
        assert _list().is_shared is False

    def test_shared_mints_a_token(self) -> None:
        shared = _list().shared()
        assert shared.is_shared is True
        assert isinstance(shared.share_token, ShareToken)

    def test_shared_is_idempotent_and_keeps_the_same_token(self) -> None:
        shared = _list().shared()
        again = shared.shared()
        # Same instance returned; the link a member copied stays valid.
        assert again is shared
        assert again.share_token == shared.share_token

    def test_unshared_clears_the_token(self) -> None:
        shared = _list().shared()
        revoked = shared.unshared()
        assert revoked.is_shared is False
        assert revoked.share_token is None

    def test_unshared_on_unshared_list_is_noop(self) -> None:
        plain = _list()
        assert plain.unshared() is plain
