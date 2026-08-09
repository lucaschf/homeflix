"""FollowSharedListUseCase - Follow a shared list by token."""

from pydantic import ValidationError

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import DomainConflictException, DomainValidationException
from src.modules.collections.application.dtos import FollowSharedListInput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.entities import ListFollow
from src.modules.collections.domain.value_objects import ShareToken
from src.shared_kernel.value_objects.profile_id import ProfileId


class FollowSharedListUseCase:
    """Follow a shared list identified by its token.

    Idempotent: a repeat follow is a no-op (the natural key stays
    unique). An unknown or revoked token yields a 404. The owner
    following their own list is rejected with a 409 — they already own
    it, and a self-follow would clutter their own list surface.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: FollowSharedListInput) -> None:
        """Create the follow if absent.

        Raises:
            ResourceNotFoundException: If the token is unknown, revoked,
                or malformed.
            DomainConflictException: If the caller owns the list.
        """
        profile_id = ProfileId(input_dto.profile_id)
        token = self._parse_token(input_dto.token)

        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_share_token(token)
            if custom_list is None or custom_list.id is None:
                raise ResourceNotFoundException.for_resource("SharedList", input_dto.token)

            if custom_list.profile_id == profile_id:
                raise DomainConflictException(
                    message="You cannot follow a list you own",
                    message_code="CUSTOM_LIST_CANNOT_FOLLOW_OWN",
                )

            existing = await uow.list_follows.find(profile_id, custom_list.id)
            if existing is None:
                await uow.list_follows.add(
                    ListFollow.create(
                        follower_profile_id=profile_id,
                        list_id=custom_list.id,
                    )
                )

    @staticmethod
    def _parse_token(raw: str) -> ShareToken:
        """Parse the token, mapping a malformed value to a 404."""
        try:
            return ShareToken(raw)
        except (DomainValidationException, ValidationError) as exc:
            raise ResourceNotFoundException.for_resource("SharedList", raw) from exc


__all__ = ["FollowSharedListUseCase"]
