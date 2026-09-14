"""Tests for Profile aggregate root."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.library_id import LibraryId
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


def _user_id() -> UserId:
    return UserId.generate()


class TestProfileCreate:
    def test_should_create_with_defaults(self):
        uid = _user_id()
        profile = Profile.create(user_id=uid, name=ProfileName("Lucas"))

        assert profile.id is None
        assert profile.user_id == uid
        assert profile.name == ProfileName("Lucas")
        assert profile.maturity_limit is None
        assert profile.is_kids is False
        assert profile.avatar_url is None

    def test_should_create_with_avatar(self):
        profile = Profile.create(
            user_id=_user_id(),
            name=ProfileName("Bia"),
            avatar_url="https://example.com/avatar.png",
        )

        assert profile.avatar_url == "https://example.com/avatar.png"

    def test_factory_should_not_accept_a_kids_flag(self):
        with pytest.raises(TypeError):
            Profile.create(  # type: ignore[call-arg]
                user_id=_user_id(), name=ProfileName("Bia"), is_kids=True
            )


class TestProfileImmutability:
    def test_should_be_frozen(self):
        profile = Profile.create(user_id=_user_id(), name=ProfileName("Lucas"))

        with pytest.raises(DomainValidationException):
            profile.name = ProfileName("Other")  # type: ignore[misc]

    def test_with_name_should_return_new_instance(self):
        original = Profile.create(user_id=_user_id(), name=ProfileName("Old"))

        renamed = original.with_name(ProfileName("New"))

        assert renamed is not original
        assert original.name == ProfileName("Old")
        assert renamed.name == ProfileName("New")

    def test_with_maturity_limit_should_return_new_instance(self):
        original = Profile.create(user_id=_user_id(), name=ProfileName("L"))

        limited = original.with_maturity_limit(AgeRating(10))

        assert limited.maturity_limit == AgeRating(10)
        assert original.maturity_limit is None

    def test_with_maturity_limit_can_clear_to_none(self):
        limited = Profile.create(user_id=_user_id(), name=ProfileName("L")).with_maturity_limit(
            AgeRating(10)
        )

        assert limited.with_maturity_limit(None).maturity_limit is None

    def test_with_avatar_should_set_url(self):
        original = Profile.create(user_id=_user_id(), name=ProfileName("L"))

        with_avatar = original.with_avatar("https://x/y.png")

        assert with_avatar.avatar_url == "https://x/y.png"

    def test_with_avatar_can_clear_to_none(self):
        original = Profile.create(
            user_id=_user_id(), name=ProfileName("L"), avatar_url="https://x/y.png"
        )

        cleared = original.with_avatar(None)

        assert cleared.avatar_url is None


class TestProfileMaturityLimit:
    """``maturity_limit`` is stored; ``is_kids`` is only ever derived from it."""

    @pytest.mark.parametrize(
        ("limit", "expected"),
        [(None, False), (0, True), (12, True), (13, False), (18, False)],
    )
    def test_is_kids_is_derived_from_the_limit(self, limit, expected):
        profile = Profile.create(user_id=_user_id(), name=ProfileName("L")).with_maturity_limit(
            None if limit is None else AgeRating(limit)
        )

        assert profile.is_kids is expected

    def test_is_kids_follows_a_limit_change(self):
        kid = Profile.create(user_id=_user_id(), name=ProfileName("L")).with_maturity_limit(
            AgeRating(12)
        )

        assert kid.is_kids is True
        assert kid.with_maturity_limit(AgeRating(14)).is_kids is False

    def test_is_kids_is_not_a_serialized_field(self):
        # A computed field would enter the dump that ``with_updates``
        # re-validates under ``extra="forbid"`` and break every ``with_*``.
        profile = Profile.create(user_id=_user_id(), name=ProfileName("L")).with_maturity_limit(
            AgeRating(12)
        )

        assert "is_kids" not in profile.model_dump()
        assert profile.model_dump()["maturity_limit"] == 12

    def test_with_helpers_preserve_the_limit(self):
        limited = Profile.create(user_id=_user_id(), name=ProfileName("L")).with_maturity_limit(
            AgeRating(14)
        )

        renamed = limited.with_name(ProfileName("New"))
        regranted = renamed.with_allowed_library_ids(["lib_movies123456"])
        reavatared = regranted.with_avatar("https://x/y.png")

        assert renamed.maturity_limit == AgeRating(14)
        assert regranted.maturity_limit == AgeRating(14)
        assert reavatared.maturity_limit == AgeRating(14)

    def test_should_reject_a_stored_kids_flag(self):
        with pytest.raises(DomainValidationException):
            Profile(user_id=_user_id(), name=ProfileName("L"), is_kids=True)  # type: ignore[call-arg]

    def test_should_reject_a_limit_off_the_scale(self):
        profile = Profile.create(user_id=_user_id(), name=ProfileName("L"))

        with pytest.raises(DomainValidationException):
            profile.with_updates(maturity_limit=22)


class TestProfileEquality:
    def test_profiles_with_same_id_should_be_equal(self):
        pid = ProfileId.generate()
        a = Profile(id=pid, user_id=_user_id(), name=ProfileName("L"))
        b = Profile(id=pid, user_id=_user_id(), name=ProfileName("Other"))

        assert a == b


class TestProfileAllowedLibraryIds:
    def test_should_default_to_empty_list_when_unset(self):
        profile = Profile.create(user_id=_user_id(), name=ProfileName("L"))

        # Default-deny — the ACL is empty, not "everything".
        assert profile.allowed_library_ids == []

    def test_should_default_to_empty_when_factory_sees_none(self):
        profile = Profile.create(
            user_id=_user_id(), name=ProfileName("L"), allowed_library_ids=None
        )

        assert profile.allowed_library_ids == []

    def test_should_accept_explicit_list_at_creation(self):
        profile = Profile.create(
            user_id=_user_id(),
            name=ProfileName("L"),
            allowed_library_ids=["lib_movies123456", "lib_series123456"],
        )

        # Raw strings are converted to typed LibraryId on assignment (ADR-018).
        assert profile.allowed_library_ids == [
            LibraryId("lib_movies123456"),
            LibraryId("lib_series123456"),
        ]

    def test_factory_should_copy_input_list(self):
        # The aggregate must not alias caller-owned lists; otherwise
        # an outside mutation would leak past the with_* boundary.
        ids = ["lib_aaaaaaaaaaaa"]
        profile = Profile.create(user_id=_user_id(), name=ProfileName("L"), allowed_library_ids=ids)
        ids.append("lib_bbbbbbbbbbbb")

        assert profile.allowed_library_ids == [LibraryId("lib_aaaaaaaaaaaa")]

    def test_should_accept_typed_library_ids_at_creation(self):
        library_id = LibraryId("lib_movies123456")

        profile = Profile.create(
            user_id=_user_id(), name=ProfileName("L"), allowed_library_ids=[library_id]
        )

        assert profile.allowed_library_ids == [library_id]

    def test_should_reject_malformed_library_id(self):
        # A malformed id must fail at write time instead of becoming a
        # silent default-deny in the catalog filter (ADR-018).
        with pytest.raises(DomainValidationException):
            Profile.create(
                user_id=_user_id(),
                name=ProfileName("L"),
                allowed_library_ids=["not-a-library-id"],
            )

    def test_with_allowed_library_ids_should_replace_entirely(self):
        original = Profile.create(
            user_id=_user_id(),
            name=ProfileName("L"),
            allowed_library_ids=["lib_oldoldoldold"],
        )

        updated = original.with_allowed_library_ids(["lib_new1new1new1", "lib_new2new2new2"])

        assert original.allowed_library_ids == [LibraryId("lib_oldoldoldold")]
        assert updated.allowed_library_ids == [
            LibraryId("lib_new1new1new1"),
            LibraryId("lib_new2new2new2"),
        ]
        assert updated is not original

    def test_with_allowed_library_ids_should_accept_empty_list_to_revoke(self):
        original = Profile.create(
            user_id=_user_id(),
            name=ProfileName("L"),
            allowed_library_ids=["lib_aaaaaaaaaaaa", "lib_bbbbbbbbbbbb"],
        )

        revoked = original.with_allowed_library_ids([])

        assert revoked.allowed_library_ids == []


class TestProfileViewingPolicy:
    """``viewing_policy()`` is the single place a profile becomes a policy."""

    def test_should_mirror_the_library_acl(self):
        profile = Profile.create(
            user_id=_user_id(),
            name=ProfileName("L"),
            allowed_library_ids=["lib_movies123456", "lib_series123456"],
        )

        policy = profile.viewing_policy()

        assert policy == ViewingPolicy(allowed_library_ids=["lib_movies123456", "lib_series123456"])
        assert policy.permits_library(LibraryId("lib_movies123456")) is True
        assert policy.permits_library(LibraryId("lib_other1234567")) is False

    def test_should_deny_everything_when_acl_is_empty(self):
        # ADR-035 §5: an empty ACL is deny-all, never a wildcard.
        profile = Profile.create(user_id=_user_id(), name=ProfileName("L"))

        assert profile.viewing_policy().denies_everything is True

    def test_should_carry_the_maturity_limit(self):
        # The age axis is wired here and nowhere else: every BC's
        # adapter returns this policy as is.
        profile = Profile.create(
            user_id=_user_id(), name=ProfileName("L"), allowed_library_ids=["lib_movies123456"]
        ).with_maturity_limit(AgeRating(12))

        policy = profile.viewing_policy()

        assert policy.maturity_limit == AgeRating(12)
        assert policy.restricts_maturity is True
        assert policy == ViewingPolicy(
            allowed_library_ids=["lib_movies123456"], maturity_limit=AgeRating(12)
        )

    def test_should_not_restrict_maturity_without_a_limit(self):
        # ``None`` is every profile that predates the limit: the age axis
        # must stay open or their catalog would change.
        profile = Profile.create(
            user_id=_user_id(), name=ProfileName("L"), allowed_library_ids=["lib_movies123456"]
        )

        policy = profile.viewing_policy()

        assert policy.restricts_maturity is False
        assert policy.maturity_limit is None

    def test_should_follow_a_limit_change(self):
        limited = Profile.create(
            user_id=_user_id(), name=ProfileName("L"), allowed_library_ids=["lib_movies123456"]
        ).with_maturity_limit(AgeRating(10))

        assert limited.with_maturity_limit(AgeRating(16)).viewing_policy().maturity_limit == (
            AgeRating(16)
        )
        assert limited.with_maturity_limit(None).viewing_policy().restricts_maturity is False

    def test_should_follow_an_acl_replacement(self):
        # Derived on every call, so a revoked library cannot linger in
        # a policy cached from the previous ACL.
        original = Profile.create(
            user_id=_user_id(), name=ProfileName("L"), allowed_library_ids=["lib_movies123456"]
        )

        revoked = original.with_allowed_library_ids([])

        assert original.viewing_policy().denies_everything is False
        assert revoked.viewing_policy().denies_everything is True
