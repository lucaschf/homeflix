"""SQLAlchemy implementation of AccessTokenRepository."""

from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.domain.repositories.access_token_repository import (
    AccessTokenRepository,
    AccessTokenSnapshot,
)
from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


class SqlAlchemyAccessTokenRepository(AccessTokenRepository):
    """Async SQLAlchemy repository for the ``access_tokens`` table.

    The same table is also accessed by FastAPI Users' built-in
    ``SQLAlchemyAccessTokenDatabase`` for the auth flow; the two
    coexist without conflict because they touch the same rows under
    one transaction. This repository covers the operations the
    application layer needs (read snapshot, switch profile, cleanup).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_token(self, token: str) -> AccessTokenSnapshot | None:
        """Resolve a token to its (user, current_profile) prefixed pair.

        Joins ``access_tokens`` with ``users`` (and LEFT-joins
        ``profiles``) so the returned snapshot carries prefixed
        external IDs — the rest of the system never sees the
        underlying UUID.
        """
        stmt = (
            select(
                AccessTokenModel.token,
                AccessTokenModel.created_at,
                UserModel.external_id.label("user_external_id"),
                ProfileModel.external_id.label("profile_external_id"),
            )
            .join(UserModel, AccessTokenModel.user_id == UserModel.id)
            .join(
                ProfileModel,
                AccessTokenModel.current_profile_id == ProfileModel.id,
                isouter=True,
            )
            .where(AccessTokenModel.token == token)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None

        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        return AccessTokenSnapshot(
            token=row.token,
            user_id=UserId(row.user_external_id),
            current_profile_id=(
                ProfileId(row.profile_external_id) if row.profile_external_id is not None else None
            ),
            created_at=created_at,
        )

    async def update_current_profile(
        self,
        token: str,
        profile_id: ProfileId | None,
    ) -> bool:
        """Set ``current_profile_id`` on the session row.

        Resolves ``profile_id`` (prefixed) to its internal UUID via
        a SELECT before issuing the UPDATE, so the rest of the layer
        deals only with prefixed VOs. Pass ``None`` to clear.
        """
        if profile_id is None:
            profile_uuid = None
        else:
            uuid_stmt = select(ProfileModel.id).where(
                ProfileModel.external_id == str(profile_id),
                ProfileModel.deleted_at.is_(None),
            )
            profile_uuid = (await self._session.execute(uuid_stmt)).scalar_one_or_none()
            if profile_uuid is None:
                raise ValueError(f"Profile {profile_id} does not exist")

        update_stmt = (
            update(AccessTokenModel)
            .where(AccessTokenModel.token == token)
            .values(current_profile_id=profile_uuid)
        )
        result = await self._session.execute(update_stmt)
        await self._session.flush()
        return bool(result.rowcount and result.rowcount > 0)

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Remove sessions whose ``created_at`` is strictly older than ``cutoff``."""
        stmt = delete(AccessTokenModel).where(AccessTokenModel.created_at < cutoff)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return int(result.rowcount or 0)


__all__ = ["SqlAlchemyAccessTokenRepository"]
