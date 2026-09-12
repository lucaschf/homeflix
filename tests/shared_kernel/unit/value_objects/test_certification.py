"""Tests for Certification value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.shared_kernel.value_objects import AgeRating, Certification, ContentRating, RatingSystem


class TestCertificationCreation:
    """Construction and the display/compare split."""

    def test_should_hold_system_label_and_age(self):
        cert = Certification(
            system=RatingSystem.BR_DEJUS,
            label=ContentRating("12"),
            minimum_age=AgeRating(12),
        )

        assert cert.system is RatingSystem.BR_DEJUS
        assert cert.label == ContentRating("12")
        assert cert.minimum_age == AgeRating(12)
        assert cert.is_determined is True

    def test_should_allow_missing_age(self):
        cert = Certification(system=RatingSystem.UNKNOWN, label=ContentRating("NR"))

        assert cert.minimum_age is None
        assert cert.is_determined is False

    def test_should_require_a_system(self):
        with pytest.raises(DomainValidationException):
            Certification(label=ContentRating("12"), minimum_age=AgeRating(12))

    def test_should_reject_unknown_field(self):
        with pytest.raises(DomainValidationException):
            Certification(
                system=RatingSystem.US_MPA,
                label=ContentRating("R"),
                rating_source="manual",
            )

    def test_should_be_immutable(self):
        cert = Certification(system=RatingSystem.US_MPA, label=ContentRating("R"))

        with pytest.raises(DomainValidationException):
            cert.minimum_age = AgeRating(17)


class TestUndeterminedFactory:
    """The shape every unrecognized label collapses to."""

    def test_should_default_to_unknown_system(self):
        cert = Certification.undetermined(ContentRating("NR"))

        assert cert.system is RatingSystem.UNKNOWN
        assert cert.minimum_age is None

    def test_should_keep_a_known_system_when_given(self):
        cert = Certification.undetermined(ContentRating("M/16"), system=RatingSystem.NUMERIC)

        assert cert.system is RatingSystem.NUMERIC
        assert cert.minimum_age is None

    def test_should_preserve_the_label(self):
        assert Certification.undetermined(ContentRating("Banned")).label.value == "Banned"


class TestCertificationEquality:
    """Value semantics."""

    def test_should_be_equal_when_all_fields_match(self):
        a = Certification(
            system=RatingSystem.US_TV, label=ContentRating("TV-MA"), minimum_age=AgeRating(17)
        )
        b = Certification(
            system=RatingSystem.US_TV, label=ContentRating("TV-MA"), minimum_age=AgeRating(17)
        )

        assert a == b

    def test_should_differ_when_system_differs(self):
        """The whole point of persisting the system: same label, different scale."""
        a = Certification(
            system=RatingSystem.US_MPA, label=ContentRating("12"), minimum_age=AgeRating(12)
        )
        b = Certification(
            system=RatingSystem.BR_DEJUS, label=ContentRating("12"), minimum_age=AgeRating(12)
        )

        assert a != b
