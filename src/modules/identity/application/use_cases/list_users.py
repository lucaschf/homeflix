"""ListUsersUseCase — paginated user list for the admin panel."""

from src.modules.identity.application.dtos.identity_dtos import (
    ListUsersInput,
    UserSummary,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.entities.user import User


class ListUsersUseCase:
    """Page through every non-deleted user, with optional role filter.

    Returns rows enriched with the profile count for each user — the
    admin list page renders that figure inline so the operator can
    eyeball households without opening detail. The count comes from
    a per-row aggregate; 50 users per page keeps that affordable
    without batching into a single SQL.
    """

    def __init__(self, uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ListUsersInput) -> list[UserSummary]:
        """Return the requested page of users."""
        async with self._uow_factory() as uow:
            users = await uow.users.list_paginated(
                # role arrives as a validated UserRole | None —
                # converted at the presentation boundary (ADR-018).
                role=input_dto.role,
                limit=input_dto.limit,
                offset=input_dto.offset,
            )

            summaries: list[UserSummary] = []
            for user in users:
                if user.id is None:
                    # Shouldn't happen — list_paginated only returns
                    # persisted rows — but the type narrowing keeps
                    # mypy happy and guards against future bugs.
                    continue
                profile_count = await uow.profiles.count_for_user(user.id)
                summaries.append(_to_summary(user, profile_count=profile_count))

        return summaries


def _to_summary(user: User, profile_count: int) -> UserSummary:
    return UserSummary(
        id=str(user.id),
        email=user.email.value,
        role=user.role.value,
        is_active=user.is_active,
        profile_count=profile_count,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


__all__ = ["ListUsersUseCase"]
