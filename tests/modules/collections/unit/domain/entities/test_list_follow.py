"""Tests for the ListFollow aggregate."""

import pytest

from src.modules.collections.domain.entities import ListFollow
from src.modules.collections.domain.value_objects import ListFollowId, ListId
from src.shared_kernel.value_objects.profile_id import ProfileId

_FOLLOWER = ProfileId("prf_follower0001")
_LIST_ID = ListId("lst_abc123def456")


@pytest.mark.unit
class TestListFollow:
    """ListFollow factory behavior."""

    def test_create_generates_prefixed_id(self) -> None:
        follow = ListFollow.create(follower_profile_id=_FOLLOWER, list_id=_LIST_ID)

        assert isinstance(follow.id, ListFollowId)
        assert follow.id.value.startswith("lfw_")
        assert follow.follower_profile_id == _FOLLOWER
        assert follow.list_id == _LIST_ID

    def test_create_sets_followed_at_via_created_at(self) -> None:
        follow = ListFollow.create(follower_profile_id=_FOLLOWER, list_id=_LIST_ID)
        assert follow.created_at is not None
