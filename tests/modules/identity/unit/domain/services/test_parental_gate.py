"""Tests for the ``ParentalGate`` domain rules (ADR-035, Amendment 7)."""

from datetime import UTC, datetime, timedelta

import pytest

from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.services import (
    UNLOCK_WINDOW,
    AdminAccess,
    LockoutPolicy,
    ParentalGate,
)
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
_OWNER = UserId.generate()


def _profile(limit: int | None) -> Profile:
    return Profile(
        id=ProfileId.generate(),
        user_id=_OWNER,
        name=ProfileName("Someone"),
        maturity_limit=None if limit is None else AgeRating(limit),
    )


def _age(value: int | None) -> AgeRating | None:
    return None if value is None else AgeRating(value)


class TestLockoutPolicy:
    def test_defaults_follow_amendment_7_d4(self) -> None:
        policy = LockoutPolicy()

        assert policy.max_attempts == 5
        assert policy.base_lock == timedelta(minutes=5)
        assert policy.max_lock == timedelta(hours=24)
        assert policy.decay == timedelta(hours=24)
        assert UNLOCK_WINDOW.total_seconds() == 300

    @pytest.mark.parametrize(
        ("lockouts", "seconds"),
        [
            (0, 300),
            (1, 600),
            (2, 1_200),
            (3, 2_400),
            (4, 4_800),
            (5, 9_600),
            (6, 19_200),
            (7, 38_400),
            (8, 76_800),
            (9, 86_400),
            (10, 86_400),
            (14, 86_400),
            (1_000, 86_400),
        ],
    )
    def test_lock_doubles_from_five_minutes_up_to_a_day(self, lockouts: int, seconds: int) -> None:
        assert LockoutPolicy().lock_duration(lockouts) == timedelta(seconds=seconds)

    @pytest.mark.parametrize("lockouts", range(15))
    def test_lock_duration_is_min_of_doubling_and_ceiling(self, lockouts: int) -> None:
        policy = LockoutPolicy(base_lock=timedelta(seconds=7), max_lock=timedelta(seconds=1_000))

        expected = min(timedelta(seconds=7) * 2**lockouts, timedelta(seconds=1_000))
        assert policy.lock_duration(lockouts) == expected

    def test_negative_step_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            LockoutPolicy().lock_duration(-1)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"max_attempts": 0},
            {"base_lock": timedelta(0)},
            {"max_lock": timedelta(minutes=1)},
            {"decay": timedelta(seconds=-1)},
            {"base_lock": timedelta(seconds=1.5)},
        ],
    )
    def test_unusable_policies_are_rejected(self, kwargs: dict[str, object]) -> None:
        with pytest.raises(ValueError):
            LockoutPolicy(**kwargs)  # type: ignore[arg-type]


class TestExceeds:
    @pytest.mark.parametrize(
        ("target", "baseline", "expected"),
        [
            pytest.param(None, 12, True, id="unrestricted-over-limited"),
            pytest.param(12, None, False, id="anything-under-unrestricted"),
            pytest.param(None, None, False, id="unrestricted-to-unrestricted"),
            pytest.param(12, 12, False, id="same-limit"),
            pytest.param(0, 0, False, id="zero-to-zero"),
            pytest.param(13, 12, True, id="one-year-higher"),
            pytest.param(11, 12, False, id="lower"),
            pytest.param(1, 0, True, id="above-a-zero-baseline"),
            pytest.param(None, 0, True, id="unrestricted-over-zero"),
            pytest.param(0, 12, False, id="zero-target"),
        ],
    )
    def test_exceeds(self, target: int | None, baseline: int | None, expected: bool) -> None:
        assert ParentalGate.exceeds(_age(target), _age(baseline)) is expected


class TestSessionLimit:
    def test_live_selected_profile_gives_its_limit(self) -> None:
        kid, parent = _profile(12), _profile(None)

        assert ParentalGate.session_limit(kid.id, [parent, kid]) == AgeRating(12)
        assert ParentalGate.session_limit(parent.id, [parent, kid]) is None

    def test_deleted_selected_profile_gives_age_zero(self) -> None:
        # A selected id missing from the live list is a soft-deleted profile,
        # never "no profile selected" — which could be unrestricted.
        parent = _profile(None)

        assert ParentalGate.session_limit(ProfileId.generate(), [parent]) == AgeRating(0)

    def test_no_profile_gives_the_lowest_limit_of_the_account(self) -> None:
        profiles = [_profile(14), _profile(None), _profile(10)]

        assert ParentalGate.session_limit(None, profiles) == AgeRating(10)

    def test_no_profile_keeps_a_zero_limit_as_the_lowest(self) -> None:
        assert ParentalGate.session_limit(None, [_profile(12), _profile(0)]) == AgeRating(0)

    @pytest.mark.parametrize("limits", [[None, None], []])
    def test_no_profile_and_no_limits_gives_unrestricted(self, limits: list[int | None]) -> None:
        assert ParentalGate.session_limit(None, [_profile(v) for v in limits]) is None


class TestAdminAccess:
    """The matrix of Amendment 7 (decision 8 widened by D10)."""

    @staticmethod
    def _decide(
        *,
        active: str,
        limits: list[int | None],
        is_write: bool,
        pin_configured: bool = True,
        unlock_until: datetime | None = None,
    ) -> AdminAccess:
        profiles = [_profile(v) for v in limits]
        active_id = {
            "none": None,
            "deleted": ProfileId.generate(),
            **{f"p{i}": p.id for i, p in enumerate(profiles)},
        }[active]
        return ParentalGate.admin_access(
            pin_configured=pin_configured,
            active_profile_id=active_id,
            account_profiles=profiles,
            unlock_until=unlock_until,
            now=_NOW,
            is_write=is_write,
        )

    @pytest.mark.parametrize(
        ("active", "limits", "read", "write"),
        [
            pytest.param("p0", [None, None], "granted", "granted", id="unrestricted-no-limits"),
            pytest.param("p0", [None, 12], "granted", "suspended", id="unrestricted-some-limit"),
            pytest.param("p1", [None, 12], "suspended", "suspended", id="limited"),
            pytest.param("p1", [None, 0], "suspended", "suspended", id="limited-at-zero"),
            pytest.param("deleted", [None, None], "suspended", "suspended", id="deleted-profile"),
            pytest.param("none", [None, 12], "suspended", "suspended", id="no-profile-some-limit"),
            pytest.param("none", [None, None], "granted", "granted", id="no-profile-no-limits"),
        ],
    )
    def test_matrix_with_a_pin_and_no_unlock(
        self, active: str, limits: list[int | None], read: str, write: str
    ) -> None:
        assert self._decide(active=active, limits=limits, is_write=False) == AdminAccess(read)
        assert self._decide(active=active, limits=limits, is_write=True) == AdminAccess(write)

    @pytest.mark.parametrize(
        ("active", "limits"),
        [("p0", [None, 12]), ("p1", [None, 12]), ("deleted", [None]), ("none", [12])],
    )
    @pytest.mark.parametrize("is_write", [False, True])
    def test_a_valid_unlock_grants_everything(
        self, active: str, limits: list[int | None], is_write: bool
    ) -> None:
        decided = self._decide(
            active=active,
            limits=limits,
            is_write=is_write,
            unlock_until=_NOW + timedelta(seconds=1),
        )

        assert decided is AdminAccess.GRANTED

    @pytest.mark.parametrize(
        "unlock_until",
        [_NOW, _NOW - timedelta(seconds=1)],
        ids=["ends-now", "passed"],
    )
    def test_an_unlock_that_is_over_grants_nothing(self, unlock_until: datetime) -> None:
        decided = self._decide(
            active="p1", limits=[None, 12], is_write=False, unlock_until=unlock_until
        )

        assert decided is AdminAccess.SUSPENDED

    @pytest.mark.parametrize("active", ["p1", "deleted", "none"])
    @pytest.mark.parametrize("is_write", [False, True])
    def test_without_a_pin_the_gate_is_inert(self, active: str, is_write: bool) -> None:
        decided = self._decide(
            active=active, limits=[None, 12], is_write=is_write, pin_configured=False
        )

        assert decided is AdminAccess.GRANTED
