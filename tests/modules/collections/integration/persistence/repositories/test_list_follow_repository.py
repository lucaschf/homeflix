"""Integration tests for SQLAlchemyListFollowRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import ListFollow
from src.modules.collections.domain.value_objects import ListId
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyListFollowRepository,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

_FOLLOWER = ProfileId("prf_follower0001")
_OTHER = ProfileId("prf_other0000001")
_LIST_A = ListId("lst_aaaa11112222")
_LIST_B = ListId("lst_bbbb33334444")


def _follow(follower: ProfileId = _FOLLOWER, list_id: ListId = _LIST_A) -> ListFollow:
    return ListFollow.create(follower_profile_id=follower, list_id=list_id)


@pytest.mark.integration
class TestSQLAlchemyListFollowRepository:
    """Persistence behavior for follows."""

    async def test_add_and_find(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyListFollowRepository(db_session)
        await repo.add(_follow())

        found = await repo.find(_FOLLOWER, _LIST_A)

        assert found is not None
        assert found.follower_profile_id == _FOLLOWER
        assert found.list_id == _LIST_A

    async def test_find_is_scoped_to_follower_and_list(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyListFollowRepository(db_session)
        await repo.add(_follow())

        assert await repo.find(_OTHER, _LIST_A) is None
        assert await repo.find(_FOLLOWER, _LIST_B) is None

    async def test_re_follow_reuses_soft_deleted_row(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyListFollowRepository(db_session)
        original = await repo.add(_follow())
        await repo.remove(_FOLLOWER, _LIST_A)

        restored = await repo.add(_follow())

        # Same underlying row is restored, not duplicated (idempotent follow).
        assert restored.id == original.id
        assert await repo.find(_FOLLOWER, _LIST_A) is not None

    async def test_remove_is_idempotent(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyListFollowRepository(db_session)
        await repo.add(_follow())

        assert await repo.remove(_FOLLOWER, _LIST_A) is True
        assert await repo.remove(_FOLLOWER, _LIST_A) is False

    async def test_list_for_follower(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyListFollowRepository(db_session)
        await repo.add(_follow(list_id=_LIST_A))
        await repo.add(_follow(list_id=_LIST_B))
        await repo.add(_follow(follower=_OTHER, list_id=_LIST_A))

        follows = await repo.list_for_follower(_FOLLOWER)

        assert {f.list_id for f in follows} == {_LIST_A, _LIST_B}

    async def test_remove_all_for_list(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyListFollowRepository(db_session)
        await repo.add(_follow(follower=_FOLLOWER, list_id=_LIST_A))
        await repo.add(_follow(follower=_OTHER, list_id=_LIST_A))
        await repo.add(_follow(follower=_FOLLOWER, list_id=_LIST_B))

        removed = await repo.remove_all_for_list(_LIST_A)

        assert removed == 2
        assert await repo.find(_FOLLOWER, _LIST_A) is None
        assert await repo.find(_OTHER, _LIST_A) is None
        # A follow of a different list is untouched.
        assert await repo.find(_FOLLOWER, _LIST_B) is not None

    async def test_delete_all_for_followers(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyListFollowRepository(db_session)
        await repo.add(_follow(follower=_FOLLOWER, list_id=_LIST_A))
        await repo.add(_follow(follower=_OTHER, list_id=_LIST_A))

        removed = await repo.delete_all_for_followers([_FOLLOWER.value])

        assert removed == 1
        assert await repo.find(_FOLLOWER, _LIST_A) is None
        assert await repo.find(_OTHER, _LIST_A) is not None

    async def test_delete_all_for_followers_empty_is_noop(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyListFollowRepository(db_session)
        assert await repo.delete_all_for_followers([]) == 0
