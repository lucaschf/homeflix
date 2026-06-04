"""DeleteAdminUserUseCase — admin soft-deletes a user account."""

import logging

from src.building_blocks.application.event_bus import EventBus
from src.modules.identity.application.dtos.identity_dtos import DeleteAdminUserInput
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.errors import (
    CannotDeleteSelfError,
    UserNotFoundException,
)
from src.modules.identity.domain.events import UserDeletedEvent
from src.modules.identity.domain.services import AdminQuorum
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.shared_kernel.value_objects.user_id import UserId

_logger = logging.getLogger(__name__)


class DeleteAdminUserUseCase:
    """Soft-delete a user; fan out cascade via ``UserDeletedEvent``.

    Guards (in order):

    * Self-delete: an admin can't remove their own row. The UI
      hides the button on the self row but the server is the
      source of truth.
    * Last-admin: deleting an ``ADMIN`` user that is the only
      active admin is refused so the operator can't lock
      themselves out.

    On success the user is soft-deleted (``deleted_at`` set) and
    ``UserDeletedEvent`` is published with the full list of
    profile ids owned by the deleted user. Cross-BC handlers in
    ``watch_progress`` and ``collections`` clean their own state.
    Event publish runs fire-and-forget — handler failures are
    logged but the user-delete still commits.
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        event_bus: EventBus,
    ) -> None:
        self._uow_factory = uow_factory
        self._event_bus = event_bus

    async def execute(self, input_dto: DeleteAdminUserInput) -> None:
        """Soft-delete the user and publish the cascade event."""
        if input_dto.user_id == input_dto.acting_admin_id:
            raise CannotDeleteSelfError(message="You cannot delete your own account")

        user_id = UserId(input_dto.user_id)

        async with self._uow_factory() as uow:
            user = await uow.users.find_by_id(user_id)
            if user is None or user.id is None:
                raise UserNotFoundException.for_resource("User", input_dto.user_id)

            if user.role is UserRole.ADMIN:
                admin_count = await uow.users.count_active_admins()
                AdminQuorum.ensure_can_remove_admin(user, admin_count)

            profiles = await uow.profiles.find_by_user(user.id)
            profile_ids = tuple(str(p.id) for p in profiles if p.id is not None)

            await uow.users.soft_delete(user_id)

        # Fan-out runs after the identity transaction commits so
        # handlers observe the soft-delete state.
        await self._event_bus.publish(
            UserDeletedEvent(user_id=str(user_id), profile_ids=profile_ids),
        )


__all__ = ["DeleteAdminUserUseCase"]
