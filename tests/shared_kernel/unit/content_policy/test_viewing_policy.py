"""Tests for ViewingPolicy — the definition the catalog query projects (ADR-035)."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import AgeRating, LibraryId

MOVIES = LibraryId("lib_movies123456")
SERIES = LibraryId("lib_series123456")
OTHER = LibraryId("lib_other1234567")


class TestViewingPolicyConstruction:
    """Construction, coercion, and the default that preserves today's behavior."""

    def test_should_accept_raw_string_library_ids(self):
        policy = ViewingPolicy(allowed_library_ids=["lib_movies123456"])

        assert policy.allowed_library_ids == (MOVIES,)

    def test_should_reject_malformed_library_id_at_construction(self):
        """A typo must fail loudly, not become an indistinguishable denial."""
        with pytest.raises(DomainValidationException):
            ViewingPolicy(allowed_library_ids=["not-a-library-id"])

    def test_should_default_to_no_maturity_limit(self):
        assert ViewingPolicy(allowed_library_ids=[MOVIES]).maturity_limit is None

    def test_should_treat_none_acl_as_empty(self):
        assert ViewingPolicy(allowed_library_ids=None).allowed_library_ids == ()

    def test_should_be_immutable(self):
        policy = ViewingPolicy(allowed_library_ids=[MOVIES])

        with pytest.raises(DomainValidationException):
            policy.maturity_limit = AgeRating(12)

    def test_unrestricted_factory_builds_a_library_only_policy(self):
        policy = ViewingPolicy.unrestricted([MOVIES, SERIES])

        assert policy.restricts_maturity is False
        assert policy.allowed_library_ids == (MOVIES, SERIES)


class TestLibraryAxis:
    """Empty ACL is deny-all, as it is today (ADR-018 §3)."""

    def test_should_deny_everything_when_acl_is_empty(self):
        policy = ViewingPolicy(allowed_library_ids=[])

        assert policy.denies_everything is True
        assert policy.permits(library_id=MOVIES, minimum_age=AgeRating(0)) is False

    def test_should_not_deny_everything_when_acl_has_entries(self):
        assert ViewingPolicy(allowed_library_ids=[MOVIES]).denies_everything is False

    def test_should_deny_library_outside_the_acl(self):
        policy = ViewingPolicy(allowed_library_ids=[MOVIES])

        assert policy.permits(library_id=OTHER, minimum_age=AgeRating(0)) is False

    def test_should_permit_library_inside_the_acl(self):
        policy = ViewingPolicy(allowed_library_ids=[MOVIES, SERIES])

        assert policy.permits(library_id=SERIES, minimum_age=AgeRating(0)) is True


class TestMaturityAxis:
    """The day-to-day axis, applied across every allowed library at once."""

    @pytest.mark.parametrize("age", [0, 10, 12])
    def test_should_permit_title_at_or_below_limit(self, age):
        policy = ViewingPolicy(allowed_library_ids=[MOVIES], maturity_limit=AgeRating(12))

        assert policy.permits(library_id=MOVIES, minimum_age=AgeRating(age)) is True

    @pytest.mark.parametrize("age", [13, 14, 18])
    def test_should_deny_title_above_limit(self, age):
        policy = ViewingPolicy(allowed_library_ids=[MOVIES], maturity_limit=AgeRating(12))

        assert policy.permits(library_id=MOVIES, minimum_age=AgeRating(age)) is False

    def test_should_deny_unrated_title_when_limited(self):
        policy = ViewingPolicy(allowed_library_ids=[MOVIES], maturity_limit=AgeRating(16))

        assert policy.permits(library_id=MOVIES, minimum_age=None) is False

    def test_should_permit_unrated_title_when_unrestricted(self):
        """No regression for the profiles that predate the feature."""
        policy = ViewingPolicy(allowed_library_ids=[MOVIES])

        assert policy.permits(library_id=MOVIES, minimum_age=None) is True

    def test_should_permit_everything_in_the_acl_when_unrestricted(self):
        policy = ViewingPolicy(allowed_library_ids=[MOVIES])

        assert policy.permits(library_id=MOVIES, minimum_age=AgeRating(18)) is True


class TestAxesCompose:
    """AND, deny-wins — neither axis can rescue a denial from the other."""

    def test_should_deny_when_only_library_allows(self):
        policy = ViewingPolicy(allowed_library_ids=[MOVIES], maturity_limit=AgeRating(10))

        assert policy.permits_library(MOVIES) is True
        assert policy.permits(library_id=MOVIES, minimum_age=AgeRating(16)) is False

    def test_should_deny_when_only_maturity_allows(self):
        policy = ViewingPolicy(allowed_library_ids=[MOVIES], maturity_limit=AgeRating(16))

        assert policy.permits_maturity(AgeRating(10)) is True
        assert policy.permits(library_id=OTHER, minimum_age=AgeRating(10)) is False

    def test_should_permit_only_when_both_allow(self):
        policy = ViewingPolicy(allowed_library_ids=[MOVIES], maturity_limit=AgeRating(16))

        assert policy.permits(library_id=MOVIES, minimum_age=AgeRating(16)) is True

    def test_empty_acl_denies_even_an_unrestricted_maturity(self):
        policy = ViewingPolicy(allowed_library_ids=[], maturity_limit=None)

        assert policy.permits(library_id=MOVIES, minimum_age=AgeRating(0)) is False


class TestViewingPolicyEquality:
    """Value semantics — two policies with the same axes are the same policy."""

    def test_should_be_equal_when_axes_match(self):
        a = ViewingPolicy(allowed_library_ids=["lib_movies123456"], maturity_limit=AgeRating(12))
        b = ViewingPolicy(allowed_library_ids=[MOVIES], maturity_limit=AgeRating(12))

        assert a == b

    def test_should_differ_when_limit_differs(self):
        a = ViewingPolicy(allowed_library_ids=[MOVIES], maturity_limit=AgeRating(12))
        b = ViewingPolicy(allowed_library_ids=[MOVIES], maturity_limit=AgeRating(14))

        assert a != b
