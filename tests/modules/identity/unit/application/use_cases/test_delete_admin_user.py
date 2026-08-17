"""Unit tests for DeleteAdminUserUseCase."""

from typing import Any

import pytest

from src.building_blocks.application.event_bus import EventBus
from src.building_blocks.domain.events import DomainEvent
from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    DeleteAdminUserInput,
)
from src.modules.identity.application.errors import (
    CannotDeleteSelfError,
    UserNotFoundException,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.delete_admin_user import (
    DeleteAdminUserUseCase,
)
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.errors import CannotDemoteLastAdminError
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.shared_kernel.integration_events import UserDeletedEvent
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory

pytestmark = pytest.mark.unit


class _RecordingEventBus(EventBus):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    def subscribe(self, event_type: type[DomainEvent], handler: Any) -> None:
        return None

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)


async def _seed(
    fake_uow: FakeIdentityUnitOfWork,
    *,
    email: str,
    role: UserRole = UserRole.MEMBER,
) -> User:
    async with fake_uow:
        return await fake_uow.users.save(User.create(email=Email(email), role=role))


class TestDeleteAdminUserUseCase:
    async def test_should_soft_delete_and_publish_event(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        admin = await _seed(fake_uow, email="root@example.com", role=UserRole.ADMIN)
        target = await _seed(fake_uow, email="m@example.com")
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        await creator.execute(CreateProfileInput(user_id=str(target.id), name="Adult"))
        await creator.execute(CreateProfileInput(user_id=str(target.id), name="Kids"))

        bus = _RecordingEventBus()
        await DeleteAdminUserUseCase(uow_factory=fake_uow_factory, event_bus=bus).execute(
            DeleteAdminUserInput(
                user_id=str(target.id),
                acting_admin_id=str(admin.id),
            ),
        )

        async with fake_uow:
            gone = await fake_uow.users.find_by_id(UserId(str(target.id)))
        assert gone is None
        assert len(bus.published) == 1
        evt = bus.published[0]
        assert isinstance(evt, UserDeletedEvent)
        assert evt.user_id == str(target.id)
        assert len(evt.profile_ids) == 2

    async def test_should_refuse_self_delete(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        admin = await _seed(fake_uow, email="root@example.com", role=UserRole.ADMIN)

        bus = _RecordingEventBus()
        with pytest.raises(CannotDeleteSelfError):
            await DeleteAdminUserUseCase(uow_factory=fake_uow_factory, event_bus=bus).execute(
                DeleteAdminUserInput(
                    user_id=str(admin.id),
                    acting_admin_id=str(admin.id),
                ),
            )
        assert bus.published == []

    async def test_should_refuse_deleting_last_active_admin(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        # Two admins recorded — but acting on the *target*, the
        # "last admin" guard sees admin_count == 1 after subtracting
        # the soft-delete target. Set up: only one admin total, and
        # a separate non-admin acting user.
        acting = await _seed(fake_uow, email="ops@example.com")
        only_admin = await _seed(fake_uow, email="root@example.com", role=UserRole.ADMIN)

        bus = _RecordingEventBus()
        with pytest.raises(CannotDemoteLastAdminError):
            await DeleteAdminUserUseCase(uow_factory=fake_uow_factory, event_bus=bus).execute(
                DeleteAdminUserInput(
                    user_id=str(only_admin.id),
                    acting_admin_id=str(acting.id),
                ),
            )

    async def test_should_raise_when_user_not_found(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        bus = _RecordingEventBus()
        with pytest.raises(UserNotFoundException):
            await DeleteAdminUserUseCase(uow_factory=fake_uow_factory, event_bus=bus).execute(
                DeleteAdminUserInput(
                    user_id=str(UserId.generate()),
                    acting_admin_id=str(UserId.generate()),
                ),
            )
