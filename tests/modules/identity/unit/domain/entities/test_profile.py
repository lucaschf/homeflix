"""Tests for Profile aggregate root."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.content_policy import ViewingPolicy
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
        assert profile.is_kids is False
        assert profile.avatar_url is None

    def test_should_create_kids_profile(self):
        profile = Profile.create(
            user_id=_user_id(),
            name=ProfileName("Bia"),
            is_kids=True,
            avatar_url="https://example.com/avatar.png",
        )

        assert profile.is_kids is True
        assert profile.avatar_url == "https://example.com/avatar.png"


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

    def test_with_kids_flag_should_return_new_instance(self):
        original = Profile.create(user_id=_user_id(), name=ProfileName("L"))

        kids = original.with_kids_flag(is_kids=True)

        assert kids.is_kids is True
        assert original.is_kids is False

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

    def test_should_not_restrict_maturity_yet(self):
        # ``Profile`` carries no maturity limit until PR 4, so the age
        # axis must stay open or every catalog read would change today.
        profile = Profile.create(
            user_id=_user_id(), name=ProfileName("L"), allowed_library_ids=["lib_movies123456"]
        )

        policy = profile.viewing_policy()

        assert policy.restricts_maturity is False
        assert policy.maturity_limit is None

    def test_should_follow_an_acl_replacement(self):
        # Derived on every call, so a revoked library cannot linger in
        # a policy cached from the previous ACL.
        original = Profile.create(
            user_id=_user_id(), name=ProfileName("L"), allowed_library_ids=["lib_movies123456"]
        )

        revoked = original.with_allowed_library_ids([])

        assert original.viewing_policy().denies_everything is False
        assert revoked.viewing_policy().denies_everything is True
