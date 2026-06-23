"""Integration tests for ``SQLAlchemyCatalogSubscriptionRepository``."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.catalog_requests.domain.entities import CatalogSubscription
from src.modules.catalog_requests.domain.value_objects import CatalogRequestId
from src.modules.catalog_requests.infrastructure.persistence.repositories import (
    SQLAlchemyCatalogSubscriptionRepository,
)

_REQ_A = CatalogRequestId("req_aaaaaaaaaaaa")
_REQ_B = CatalogRequestId("req_bbbbbbbbbbbb")
_USER_1 = "usr_111111111111"
_USER_2 = "usr_222222222222"


def _repo(session: AsyncSession) -> SQLAlchemyCatalogSubscriptionRepository:
    return SQLAlchemyCatalogSubscriptionRepository(session)


class TestAddAndFind:
    async def test_add_then_find_round_trips(self, db_session: AsyncSession) -> None:
        repo = _repo(db_session)
        saved = await repo.add(CatalogSubscription.create(_REQ_A, _USER_1))

        assert saved.id is not None
        assert str(saved.id).startswith("sub_")

        found = await repo.find(_REQ_A, _USER_1)
        assert found is not None
        assert found.request_id == _REQ_A
        assert found.user_id == _USER_1

    async def test_find_misses_on_wrong_user(self, db_session: AsyncSession) -> None:
        repo = _repo(db_session)
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_1))

        assert await repo.find(_REQ_A, _USER_2) is None

    async def test_find_ignores_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = _repo(db_session)
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_1))
        await repo.remove(_REQ_A, _USER_1)

        assert await repo.find(_REQ_A, _USER_1) is None


class TestListForRequest:
    async def test_lists_active_only_for_the_request(self, db_session: AsyncSession) -> None:
        repo = _repo(db_session)
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_1))
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_2))
        await repo.add(CatalogSubscription.create(_REQ_B, _USER_1))
        await repo.remove(_REQ_A, _USER_2)

        subs = await repo.list_for_request(_REQ_A)

        assert {s.user_id for s in subs} == {_USER_1}


class TestRemove:
    async def test_remove_is_idempotent(self, db_session: AsyncSession) -> None:
        repo = _repo(db_session)
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_1))

        assert await repo.remove(_REQ_A, _USER_1) is True
        assert await repo.remove(_REQ_A, _USER_1) is False


class TestCounts:
    async def test_count_for_request_excludes_deleted(self, db_session: AsyncSession) -> None:
        repo = _repo(db_session)
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_1))
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_2))
        await repo.remove(_REQ_A, _USER_2)

        assert await repo.count_for_request(_REQ_A) == 1

    async def test_count_by_requests_batches(self, db_session: AsyncSession) -> None:
        repo = _repo(db_session)
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_1))
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_2))
        await repo.add(CatalogSubscription.create(_REQ_B, _USER_1))

        counts = await repo.count_by_requests([_REQ_A, _REQ_B])

        assert counts == {_REQ_A: 2, _REQ_B: 1}

    async def test_count_by_requests_empty_input(self, db_session: AsyncSession) -> None:
        repo = _repo(db_session)
        assert await repo.count_by_requests([]) == {}


class TestRequestIdsForUser:
    async def test_returns_active_request_ids(self, db_session: AsyncSession) -> None:
        repo = _repo(db_session)
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_1))
        await repo.add(CatalogSubscription.create(_REQ_B, _USER_1))
        await repo.add(CatalogSubscription.create(_REQ_A, _USER_2))
        await repo.remove(_REQ_B, _USER_1)

        assert await repo.request_ids_for_user(_USER_1) == {_REQ_A}
