"""SQLAlchemy implementation of AccessTokenRepository."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, delete, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.domain.repositories.access_token_repository import (
    AccessTokenRepository,
    AccessTokenSnapshot,
    ParentalSessionState,
    PinAttemptReservation,
)
from src.modules.identity.domain.services.parental_gate import LockoutPolicy
from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


def _to_epoch(moment: datetime) -> int:
    """Convert an aware datetime to whole epoch seconds (floor).

    Raises:
        ValueError: If ``moment`` is naive — its epoch would silently
            depend on the machine's local timezone.
    """
    if moment.tzinfo is None:
        raise ValueError("parental lockout times must be timezone-aware")
    return int(moment.timestamp())


def _from_epoch(seconds: int | None) -> datetime | None:
    return None if seconds is None else datetime.fromtimestamp(seconds, UTC)


def _whole_seconds(duration: timedelta) -> int:
    return int(duration.total_seconds())


class SqlAlchemyAccessTokenRepository(AccessTokenRepository):
    """Async SQLAlchemy repository for the ``access_tokens`` table.

    The same table is also accessed by FastAPI Users' built-in
    ``SQLAlchemyAccessTokenDatabase`` for the auth flow; the two
    coexist without conflict because they touch the same rows under
    one transaction. This repository covers the operations the
    application layer needs (read snapshot, switch profile, cleanup,
    parental unlock and lockout).

    The parental writes are single ``UPDATE`` statements whose ``WHERE``
    carries the condition, and a conditional one reports success by the
    row its ``RETURNING`` yields. ``rowcount`` cannot be used for that:
    with ``RETURNING`` on this stack (aiosqlite) it is ``-1`` whether a
    row matched or not.
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
            select(  # type: ignore[call-overload]  # fastapi-users typing
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
        """Set ``current_profile_id`` on the session row and close its unlock window.

        Resolves ``profile_id`` (prefixed) to its internal UUID via
        a SELECT before issuing the UPDATE, so the rest of the layer
        deals only with prefixed VOs. Pass ``None`` to clear. The same
        UPDATE sets ``parental_unlock_until`` to NULL (ADR-035, Amendment
        7 D9).
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
            .where(AccessTokenModel.token == token)  # type: ignore[arg-type]  # fastapi-users typing
            .values(current_profile_id=profile_uuid, parental_unlock_until=None)
        )
        result = await self._session.execute(update_stmt)
        await self._session.flush()
        return bool(result.rowcount and result.rowcount > 0)  # type: ignore[attr-defined]  # SQLAlchemy DML CursorResult

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Remove sessions whose ``created_at`` is strictly older than ``cutoff``."""
        stmt = delete(AccessTokenModel).where(AccessTokenModel.created_at < cutoff)  # type: ignore[arg-type]  # fastapi-users typing
        result = await self._session.execute(stmt)
        await self._session.flush()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]  # SQLAlchemy DML CursorResult

    async def get_parental_state(self, token: str) -> ParentalSessionState | None:
        """Read the session's parental state, with the selected profile as stored.

        The profile is LEFT-joined without a ``deleted_at`` filter, so a
        session pointing at a soft-deleted profile still reports its id.
        """
        stmt = (
            select(
                UserModel.external_id.label("user_external_id"),
                ProfileModel.external_id.label("profile_external_id"),
                AccessTokenModel.parental_failed_attempts,
                AccessTokenModel.parental_lockouts,
                AccessTokenModel.parental_locked_until,
                AccessTokenModel.parental_unlock_until,
            )
            .join(UserModel, AccessTokenModel.user_id == UserModel.id)
            .join(
                ProfileModel,
                AccessTokenModel.current_profile_id == ProfileModel.id,
                isouter=True,
            )
            .where(AccessTokenModel.token == token)  # type: ignore[arg-type]  # fastapi-users typing
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return ParentalSessionState(
            user_id=UserId(row.user_external_id),
            current_profile_id=(
                ProfileId(row.profile_external_id) if row.profile_external_id is not None else None
            ),
            failed_attempts=row.parental_failed_attempts,
            lockouts=row.parental_lockouts,
            locked_until=_from_epoch(row.parental_locked_until),
            unlock_until=_from_epoch(row.parental_unlock_until),
        )

    async def reserve_pin_attempt(
        self,
        token: str,
        *,
        now: datetime,
        policy: LockoutPolicy,
    ) -> PinAttemptReservation:
        """Count one attempt with a single ``UPDATE ... RETURNING``.

        SQLite evaluates every ``SET`` expression against the row as it was
        before the statement, so each expression below recomputes the
        effective counter and ladder step instead of reading a column the
        same statement has just changed. The lock length is
        ``policy.lock_duration`` projected into SQL: ``base << step`` below
        the policy's saturation step, ``max_lock`` from it on.
        """
        t = AccessTokenModel
        now_s = _to_epoch(now)
        max_attempts = policy.max_attempts

        # A lock that has passed restarts the counter; the ladder returns to
        # step zero once ``decay`` has passed since the end of the last lock.
        lock_passed = and_(t.parental_locked_until.is_not(None), t.parental_locked_until <= now_s)
        eff_attempts = case(
            (and_(lock_passed, t.parental_failed_attempts >= max_attempts), 0),
            else_=t.parental_failed_attempts,
        )
        ladder_decayed = and_(
            t.parental_locked_until.is_not(None),
            t.parental_locked_until + _whole_seconds(policy.decay) <= now_s,
        )
        eff_lockouts = case((ladder_decayed, 0), else_=t.parental_lockouts)

        starts_lock = eff_attempts + 1 >= max_attempts
        lock_seconds = case(
            (eff_lockouts >= policy.saturation_step, _whole_seconds(policy.max_lock)),
            else_=literal(_whole_seconds(policy.base_lock)).op("<<")(eff_lockouts),
        )
        stmt = (
            update(t)
            .where(
                t.token == token,  # type: ignore[arg-type]  # fastapi-users typing
                or_(t.parental_locked_until.is_(None), t.parental_locked_until <= now_s),
            )
            .values(
                parental_failed_attempts=eff_attempts + 1,
                parental_lockouts=case((starts_lock, eff_lockouts + 1), else_=eff_lockouts),
                parental_locked_until=case(
                    (starts_lock, now_s + lock_seconds),
                    else_=t.parental_locked_until,
                ),
            )
            .returning(t.parental_failed_attempts, t.parental_locked_until)
            .execution_options(synchronize_session=False)
        )
        granted = (await self._session.execute(stmt)).first()
        if granted is not None:
            # The WHERE admitted only rows unlocked at ``now``, so a lock
            # ending after ``now`` was started by this attempt.
            started = granted.parental_locked_until
            return PinAttemptReservation(
                granted=True,
                failed_attempts=granted.parental_failed_attempts,
                locked_until=_from_epoch(started)
                if started is not None and started > now_s
                else None,
            )

        denied = (
            await self._session.execute(
                select(t.parental_failed_attempts, t.parental_locked_until).where(
                    t.token == token  # type: ignore[arg-type]  # fastapi-users typing
                )
            )
        ).first()
        if denied is None:
            return PinAttemptReservation(granted=False, failed_attempts=0, locked_until=None)
        return PinAttemptReservation(
            granted=False,
            failed_attempts=denied.parental_failed_attempts,
            locked_until=_from_epoch(denied.parental_locked_until),
        )

    async def record_pin_success(
        self,
        token: str,
        *,
        now: datetime,
        unlock_until: datetime,
    ) -> None:
        """Clear the attempts, open the window and end a lock in force at ``now``."""
        t = AccessTokenModel
        now_s = _to_epoch(now)
        stmt = (
            update(t)
            .where(t.token == token)  # type: ignore[arg-type]  # fastapi-users typing
            .values(
                parental_failed_attempts=0,
                parental_unlock_until=_to_epoch(unlock_until),
                parental_locked_until=case(
                    (t.parental_locked_until > now_s, now_s),
                    else_=t.parental_locked_until,
                ),
            )
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(stmt)

    async def consume_unlock(self, token: str, *, now: datetime) -> bool:
        """Close a window still open at ``now``; consumed when a row comes back."""
        t = AccessTokenModel
        stmt = (
            update(t)
            .where(
                t.token == token,  # type: ignore[arg-type]  # fastapi-users typing
                t.parental_unlock_until > _to_epoch(now),
            )
            .values(parental_unlock_until=None)
            .returning(t.token)  # type: ignore[call-overload]  # fastapi-users typing
            .execution_options(synchronize_session=False)
        )
        return (await self._session.execute(stmt)).first() is not None

    async def clear_unlock(self, token: str) -> None:
        """Set only ``parental_unlock_until`` to NULL."""
        stmt = (
            update(AccessTokenModel)
            .where(AccessTokenModel.token == token)  # type: ignore[arg-type]  # fastapi-users typing
            .values(parental_unlock_until=None)
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(stmt)


__all__ = ["SqlAlchemyAccessTokenRepository"]
