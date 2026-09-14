"""Integration tests for SqlAlchemyAccessTokenRepository."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.services.parental_gate import LockoutPolicy
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.profile_id import ProfileId


def _new_token() -> str:
    """Mimic FastAPI Users' default token generation (43 base64url chars)."""
    return secrets.token_urlsafe(32)


async def _seed_user(
    uow_factory: IdentityUnitOfWorkFactory,
    email: str = "owner@example.com",
) -> User:
    async with uow_factory() as uow:
        return await uow.users.save(User.create(email=Email(email), hashed_password="hp"))


async def _user_uuid(db_session: AsyncSession, external_id: str) -> uuid.UUID:
    result = await db_session.execute(
        select(UserModel.id).where(UserModel.external_id == external_id)
    )
    return result.scalar_one()


async def _profile_uuid(db_session: AsyncSession, external_id: str) -> uuid.UUID:
    result = await db_session.execute(
        select(ProfileModel.id).where(ProfileModel.external_id == external_id)
    )
    return result.scalar_one()


async def _insert_access_token(
    db_session: AsyncSession,
    *,
    token: str,
    user_uuid: uuid.UUID,
    current_profile_uuid: uuid.UUID | None = None,
    created_at: datetime | None = None,
    failed_attempts: int | None = None,
    lockouts: int | None = None,
    locked_until: int | None = None,
    unlock_until: int | None = None,
) -> None:
    row = AccessTokenModel(
        token=token,
        user_id=user_uuid,
        current_profile_id=current_profile_uuid,
        parental_locked_until=locked_until,
        parental_unlock_until=unlock_until,
    )
    if created_at is not None:
        row.created_at = created_at
    # Left unset, the counters come from the column's server default.
    if failed_attempts is not None:
        row.parental_failed_attempts = failed_attempts
    if lockouts is not None:
        row.parental_lockouts = lockouts
    db_session.add(row)
    await db_session.commit()


_NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)
_POLICY = LockoutPolicy()


def _epoch(moment: datetime) -> int:
    return int(moment.timestamp())


async def _parental_row(db_session: AsyncSession, token: str) -> Row[Any]:
    db_session.expire_all()
    result = await db_session.execute(
        select(
            AccessTokenModel.parental_failed_attempts,
            AccessTokenModel.parental_lockouts,
            AccessTokenModel.parental_locked_until,
            AccessTokenModel.parental_unlock_until,
        ).where(AccessTokenModel.token == token)
    )
    return result.one()


async def _session_for_new_user(
    uow_factory: IdentityUnitOfWorkFactory,
    db_session: AsyncSession,
    email: str = "owner@example.com",
    **columns: Any,
) -> str:
    owner = await _seed_user(uow_factory, email=email)
    assert owner.id is not None
    token = _new_token()
    await _insert_access_token(
        db_session,
        token=token,
        user_uuid=await _user_uuid(db_session, owner.id.value),
        **columns,
    )
    return token


class TestGetByToken:
    async def test_should_return_snapshot_with_prefixed_user_id(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None
        owner_uuid = await _user_uuid(db_session, owner.id.value)
        token = _new_token()
        await _insert_access_token(db_session, token=token, user_uuid=owner_uuid)

        async with uow_factory() as uow:
            snap = await uow.access_tokens.get_by_token(token)

        assert snap is not None
        assert snap.token == token
        assert snap.user_id == owner.id
        assert snap.current_profile_id is None
        assert snap.created_at.tzinfo is not None

    async def test_should_resolve_current_profile_to_prefixed_id(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            profile = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Lucas"))
            )

        owner_uuid = await _user_uuid(db_session, owner.id.value)
        assert profile.id is not None
        profile_uuid = await _profile_uuid(db_session, profile.id.value)
        token = _new_token()
        await _insert_access_token(
            db_session,
            token=token,
            user_uuid=owner_uuid,
            current_profile_uuid=profile_uuid,
        )

        async with uow_factory() as uow:
            snap = await uow.access_tokens.get_by_token(token)

        assert snap is not None
        assert snap.current_profile_id == profile.id

    async def test_should_return_none_for_unknown_token(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            snap = await uow.access_tokens.get_by_token("nonexistent")

        assert snap is None


class TestUpdateCurrentProfile:
    async def test_should_set_active_profile_on_existing_session(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            profile = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Lucas"))
            )

        owner_uuid = await _user_uuid(db_session, owner.id.value)
        token = _new_token()
        await _insert_access_token(db_session, token=token, user_uuid=owner_uuid)

        assert profile.id is not None
        async with uow_factory() as uow:
            ok = await uow.access_tokens.update_current_profile(token, profile.id)

        assert ok is True
        async with uow_factory() as uow:
            snap = await uow.access_tokens.get_by_token(token)
        assert snap is not None
        assert snap.current_profile_id == profile.id

    async def test_should_clear_active_profile_when_passing_none(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            profile = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Lucas"))
            )

        owner_uuid = await _user_uuid(db_session, owner.id.value)
        assert profile.id is not None
        profile_uuid = await _profile_uuid(db_session, profile.id.value)
        token = _new_token()
        await _insert_access_token(
            db_session,
            token=token,
            user_uuid=owner_uuid,
            current_profile_uuid=profile_uuid,
        )

        async with uow_factory() as uow:
            ok = await uow.access_tokens.update_current_profile(token, None)

        assert ok is True
        async with uow_factory() as uow:
            snap = await uow.access_tokens.get_by_token(token)
        assert snap is not None
        assert snap.current_profile_id is None

    @pytest.mark.parametrize("to_profile", [True, False], ids=["to-a-profile", "to-none"])
    async def test_should_close_the_parental_unlock_window(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
        to_profile: bool,
    ):
        # Every switch starts the new profile without a leftover unlock
        # (ADR-035, Amendment 7 D9), and earns no PIN attempts: the
        # lockout state is left as it was.
        owner = await _seed_user(uow_factory)
        assert owner.id is not None
        async with uow_factory() as uow:
            profile = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Lucas"))
            )
        assert profile.id is not None
        locked_until = _epoch(_NOW + timedelta(minutes=10))
        token = _new_token()
        await _insert_access_token(
            db_session,
            token=token,
            user_uuid=await _user_uuid(db_session, owner.id.value),
            failed_attempts=4,
            lockouts=2,
            locked_until=locked_until,
            unlock_until=_epoch(_NOW + timedelta(minutes=5)),
        )

        async with uow_factory() as uow:
            ok = await uow.access_tokens.update_current_profile(
                token, profile.id if to_profile else None
            )

        assert ok is True
        assert tuple(await _parental_row(db_session, token)) == (4, 2, locked_until, None)

    async def test_should_return_false_when_token_does_not_exist(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            ok = await uow.access_tokens.update_current_profile("ghost-token", profile_id=None)

        assert ok is False

    async def test_should_raise_when_profile_does_not_exist(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None
        owner_uuid = await _user_uuid(db_session, owner.id.value)
        token = _new_token()
        await _insert_access_token(db_session, token=token, user_uuid=owner_uuid)

        with pytest.raises(ValueError, match="does not exist"):
            async with uow_factory() as uow:
                await uow.access_tokens.update_current_profile(token, ProfileId.generate())


class TestDeleteOlderThan:
    async def test_should_remove_sessions_older_than_cutoff(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None
        owner_uuid = await _user_uuid(db_session, owner.id.value)

        now = datetime.now(UTC)
        old_token = _new_token()
        recent_token = _new_token()
        await _insert_access_token(
            db_session,
            token=old_token,
            user_uuid=owner_uuid,
            created_at=now - timedelta(days=100),
        )
        await _insert_access_token(
            db_session,
            token=recent_token,
            user_uuid=owner_uuid,
            created_at=now - timedelta(days=10),
        )

        cutoff = now - timedelta(days=90)
        async with uow_factory() as uow:
            removed = await uow.access_tokens.delete_older_than(cutoff)

        assert removed == 1

        async with uow_factory() as uow:
            assert await uow.access_tokens.get_by_token(old_token) is None
            assert await uow.access_tokens.get_by_token(recent_token) is not None

    async def test_should_return_zero_when_no_sessions_match(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            removed = await uow.access_tokens.delete_older_than(
                datetime.now(UTC) - timedelta(days=365)
            )

        assert removed == 0


class TestParentalColumnDefaults:
    async def test_new_session_starts_with_zero_counters_and_no_windows(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        # Inserted like the FastAPI Users login does: token and user only.
        token = await _session_for_new_user(uow_factory, db_session)

        row = await _parental_row(db_session, token)

        assert tuple(row) == (0, 0, None, None)


class TestGetParentalState:
    async def test_should_read_the_state_with_prefixed_ids(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None
        async with uow_factory() as uow:
            profile = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Lucas"))
            )
        assert profile.id is not None
        token = _new_token()
        await _insert_access_token(
            db_session,
            token=token,
            user_uuid=await _user_uuid(db_session, owner.id.value),
            current_profile_uuid=await _profile_uuid(db_session, profile.id.value),
            failed_attempts=3,
            lockouts=2,
            locked_until=_epoch(_NOW),
            unlock_until=_epoch(_NOW + timedelta(minutes=5)),
        )

        async with uow_factory() as uow:
            state = await uow.access_tokens.get_parental_state(token)

        assert state is not None
        assert state.user_id == owner.id
        assert state.current_profile_id == profile.id
        assert (state.failed_attempts, state.lockouts) == (3, 2)
        assert state.locked_until == _NOW
        assert state.unlock_until == _NOW + timedelta(minutes=5)

    async def test_should_keep_the_id_of_a_soft_deleted_profile(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        # A deleted selection must not read as "no profile selected".
        owner = await _seed_user(uow_factory)
        assert owner.id is not None
        async with uow_factory() as uow:
            profile = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Kid"))
            )
        assert profile.id is not None
        token = _new_token()
        await _insert_access_token(
            db_session,
            token=token,
            user_uuid=await _user_uuid(db_session, owner.id.value),
            current_profile_uuid=await _profile_uuid(db_session, profile.id.value),
        )
        async with uow_factory() as uow:
            assert await uow.profiles.delete(profile.id) is True

        async with uow_factory() as uow:
            state = await uow.access_tokens.get_parental_state(token)

        assert state is not None
        assert state.current_profile_id == profile.id

    async def test_should_return_none_for_unknown_token(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            assert await uow.access_tokens.get_parental_state("ghost-token") is None


class TestReservePinAttempt:
    async def test_granted_reservations_come_back_through_returning(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        token = await _session_for_new_user(uow_factory, db_session)

        reservations = []
        for _ in range(4):
            async with uow_factory() as uow:
                reservations.append(
                    await uow.access_tokens.reserve_pin_attempt(token, now=_NOW, policy=_POLICY)
                )

        assert [(r.granted, r.failed_attempts, r.locked_until) for r in reservations] == [
            (True, 1, None),
            (True, 2, None),
            (True, 3, None),
            (True, 4, None),
        ]

    async def test_attempt_reaching_the_budget_starts_the_lock_and_the_next_is_denied(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        token = await _session_for_new_user(uow_factory, db_session, failed_attempts=4)

        async with uow_factory() as uow:
            fifth = await uow.access_tokens.reserve_pin_attempt(token, now=_NOW, policy=_POLICY)
        async with uow_factory() as uow:
            sixth = await uow.access_tokens.reserve_pin_attempt(
                token, now=_NOW + timedelta(seconds=299), policy=_POLICY
            )

        lock_end = _NOW + timedelta(seconds=300)
        assert (fifth.granted, fifth.failed_attempts, fifth.locked_until) == (True, 5, lock_end)
        assert (sixth.granted, sixth.failed_attempts, sixth.locked_until) == (False, 5, lock_end)
        assert tuple(await _parental_row(db_session, token)) == (5, 1, _epoch(lock_end), None)

    @pytest.mark.parametrize("lockouts", range(15))
    async def test_sql_lock_length_matches_the_domain_policy(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
        lockouts: int,
    ):
        token = await _session_for_new_user(
            uow_factory, db_session, failed_attempts=4, lockouts=lockouts
        )

        async with uow_factory() as uow:
            reservation = await uow.access_tokens.reserve_pin_attempt(
                token, now=_NOW, policy=_POLICY
            )

        assert reservation.locked_until is not None
        assert reservation.locked_until - _NOW == _POLICY.lock_duration(lockouts)
        assert (await _parental_row(db_session, token)).parental_lockouts == lockouts + 1

    async def test_lock_on_one_device_leaves_the_other_device_free(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None
        owner_uuid = await _user_uuid(db_session, owner.id.value)
        tablet, tv = _new_token(), _new_token()
        await _insert_access_token(
            db_session,
            token=tablet,
            user_uuid=owner_uuid,
            failed_attempts=5,
            lockouts=1,
            locked_until=_epoch(_NOW + timedelta(minutes=5)),
        )
        await _insert_access_token(db_session, token=tv, user_uuid=owner_uuid)

        async with uow_factory() as uow:
            on_tablet = await uow.access_tokens.reserve_pin_attempt(
                tablet, now=_NOW, policy=_POLICY
            )
            on_tv = await uow.access_tokens.reserve_pin_attempt(tv, now=_NOW, policy=_POLICY)

        assert on_tablet.granted is False
        assert (on_tv.granted, on_tv.failed_attempts) == (True, 1)

    async def test_unknown_token_is_denied_without_a_lock(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            reservation = await uow.access_tokens.reserve_pin_attempt(
                "ghost-token", now=_NOW, policy=_POLICY
            )

        assert (reservation.granted, reservation.locked_until) == (False, None)


class TestRecordPinSuccess:
    async def test_opens_the_window_clears_attempts_and_ends_the_lock_it_started(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        token = await _session_for_new_user(uow_factory, db_session, failed_attempts=4, lockouts=2)
        async with uow_factory() as uow:
            reservation = await uow.access_tokens.reserve_pin_attempt(
                token, now=_NOW, policy=_POLICY
            )
        assert reservation.locked_until == _NOW + _POLICY.lock_duration(2)

        async with uow_factory() as uow:
            await uow.access_tokens.record_pin_success(
                token, now=_NOW, unlock_until=_NOW + timedelta(minutes=5)
            )

        # Attempts cleared, lock ended at now (its end kept for the decay),
        # the ladder step kept, the window open.
        assert tuple(await _parental_row(db_session, token)) == (
            0,
            3,
            _epoch(_NOW),
            _epoch(_NOW + timedelta(minutes=5)),
        )

    async def test_keeps_the_end_of_a_lock_that_already_passed(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        passed = _epoch(_NOW - timedelta(hours=1))
        token = await _session_for_new_user(
            uow_factory, db_session, failed_attempts=2, lockouts=1, locked_until=passed
        )

        async with uow_factory() as uow:
            await uow.access_tokens.record_pin_success(
                token, now=_NOW, unlock_until=_NOW + timedelta(minutes=5)
            )

        row = await _parental_row(db_session, token)
        assert (row.parental_failed_attempts, row.parental_lockouts) == (0, 1)
        assert row.parental_locked_until == passed


class TestConsumeUnlock:
    async def test_a_valid_window_is_consumed_once(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        token = await _session_for_new_user(
            uow_factory, db_session, unlock_until=_epoch(_NOW + timedelta(minutes=5))
        )

        async with uow_factory() as uow:
            first = await uow.access_tokens.consume_unlock(token, now=_NOW)
        async with uow_factory() as uow:
            second = await uow.access_tokens.consume_unlock(token, now=_NOW)

        assert (first, second) == (True, False)
        assert (await _parental_row(db_session, token)).parental_unlock_until is None

    @pytest.mark.parametrize(
        "unlock_until",
        [_NOW, _NOW - timedelta(seconds=1), None],
        ids=["ends-now", "passed", "never-opened"],
    )
    async def test_a_window_that_is_not_open_at_now_is_not_consumed(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
        unlock_until: datetime | None,
    ):
        stored = None if unlock_until is None else _epoch(unlock_until)
        token = await _session_for_new_user(uow_factory, db_session, unlock_until=stored)

        async with uow_factory() as uow:
            consumed = await uow.access_tokens.consume_unlock(token, now=_NOW)

        assert consumed is False
        assert (await _parental_row(db_session, token)).parental_unlock_until == stored


class TestClearUnlock:
    async def test_only_the_window_is_cleared(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        locked_until = _epoch(_NOW + timedelta(minutes=10))
        token = await _session_for_new_user(
            uow_factory,
            db_session,
            failed_attempts=5,
            lockouts=2,
            locked_until=locked_until,
            unlock_until=_epoch(_NOW + timedelta(minutes=5)),
        )

        async with uow_factory() as uow:
            await uow.access_tokens.clear_unlock(token)

        assert tuple(await _parental_row(db_session, token)) == (5, 2, locked_until, None)
