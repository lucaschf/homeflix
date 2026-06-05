"""Tests for Profile aggregate root."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.value_objects.profile_name import ProfileName
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
