"""Tests for ContentRatingPolicy — jurisdiction selection (ADR-035).

The behaviour these cover used to live in ``TmdbResponseMapper``, where
the jurisdiction was inferred from ``supported_locales`` as a proxy.
It is domain policy, so it moved here; the adapter now only reports what
each board said.
"""

import pytest

from src.modules.media.domain.services import ContentRatingPolicy
from src.shared_kernel.content_policy import ContentRatingFallback
from src.shared_kernel.value_objects import AgeRating, RatingSystem

BR_THEN_US = ("BR", "US")


@pytest.mark.unit
class TestPreferredJurisdiction:
    """The first preferred board that rated the title wins."""

    def test_should_prefer_the_first_listed_jurisdiction(self):
        chosen = ContentRatingPolicy.select(
            {"US": "PG-13", "BR": "14"},
            jurisdictions=BR_THEN_US,
        )

        assert chosen.minimum_age == AgeRating(14)
        assert chosen.system is RatingSystem.BR_DEJUS

    def test_should_fall_through_to_the_next_preference(self):
        chosen = ContentRatingPolicy.select({"US": "PG-13"}, jurisdictions=BR_THEN_US)

        assert chosen.minimum_age == AgeRating(13)
        assert chosen.system is RatingSystem.US_MPA

    def test_should_honour_a_reordered_preference(self):
        """The household's order is the whole point of the setting."""
        chosen = ContentRatingPolicy.select(
            {"US": "R", "BR": "16"},
            jurisdictions=("US", "BR"),
        )

        assert chosen.minimum_age == AgeRating(17)

    def test_should_attribute_the_scale_from_the_country(self):
        """A bare numeral is Brazilian here because the board that issued it is."""
        chosen = ContentRatingPolicy.select({"BR": "12"}, jurisdictions=("BR",))

        assert chosen.system is RatingSystem.BR_DEJUS

    def test_should_be_case_insensitive_about_country_codes(self):
        chosen = ContentRatingPolicy.select({"br": "14"}, jurisdictions=("BR",))

        assert chosen.minimum_age == AgeRating(14)

    def test_should_stop_at_a_preferred_board_that_says_unrated(self):
        """A board that reviewed the title and said NR has spoken.

        Falling through to the next jurisdiction would quietly overrule
        the one the household chose.
        """
        chosen = ContentRatingPolicy.select(
            {"BR": "NR", "US": "PG"},
            jurisdictions=BR_THEN_US,
        )

        assert chosen.is_determined is False
        assert chosen.label.value == "NR"


@pytest.mark.unit
class TestFallback:
    """What happens when no preferred board rated the title."""

    def test_strictest_available_should_pick_the_highest_age(self):
        chosen = ContentRatingPolicy.select(
            {"FR": "12", "DE": "16"},
            jurisdictions=BR_THEN_US,
        )

        assert chosen.minimum_age == AgeRating(16)

    def test_strictest_available_is_the_default(self):
        chosen = ContentRatingPolicy.select({"FR": "12"}, jurisdictions=BR_THEN_US)

        assert chosen.minimum_age == AgeRating(12)

    def test_none_fallback_should_leave_it_undetermined(self):
        chosen = ContentRatingPolicy.select(
            {"FR": "12"},
            jurisdictions=BR_THEN_US,
            fallback=ContentRatingFallback.NONE,
        )

        assert chosen is None

    def test_should_ignore_unrated_labels_when_taking_the_strictest(self):
        chosen = ContentRatingPolicy.select(
            {"FR": "NR", "DE": "12"},
            jurisdictions=BR_THEN_US,
        )

        assert chosen.minimum_age == AgeRating(12)

    def test_should_keep_the_label_when_no_board_yields_an_age(self):
        """Gating is identical either way; dropping it would erase the badge.

        A title every board marked ``NR`` was still reviewed. Returning
        nothing would hide it from limited profiles exactly the same way
        — undetermined resolves to adult — while also erasing the rating
        from the UI, which ADR-035 says must not change.
        """
        chosen = ContentRatingPolicy.select({"FR": "NR"}, jurisdictions=BR_THEN_US)

        assert chosen is not None
        assert chosen.is_determined is False
        assert chosen.label.value == "NR"

    def test_should_prefer_a_board_with_an_age_over_an_unrated_one(self):
        chosen = ContentRatingPolicy.select({"AR": "NR", "FR": "12"}, jurisdictions=BR_THEN_US)

        assert chosen.minimum_age == AgeRating(12)

    def test_none_fallback_still_returns_nothing_for_unrated_boards(self):
        chosen = ContentRatingPolicy.select(
            {"FR": "NR"},
            jurisdictions=BR_THEN_US,
            fallback=ContentRatingFallback.NONE,
        )

        assert chosen is None

    def test_empty_preference_takes_the_fallback_path(self):
        """No configured preference means the strictest board wins."""
        chosen = ContentRatingPolicy.select({"US": "R", "BR": "16"}, jurisdictions=())

        assert chosen.minimum_age == AgeRating(17)

    def test_should_be_deterministic_when_two_boards_tie(self):
        """Dict order from the provider must not decide which system is stored."""
        first = ContentRatingPolicy.select({"DE": "16", "FR": "16"}, jurisdictions=())
        second = ContentRatingPolicy.select({"FR": "16", "DE": "16"}, jurisdictions=())

        assert first == second


@pytest.mark.unit
class TestDegenerateInput:
    """The provider is not always tidy."""

    def test_should_return_none_for_an_empty_map(self):
        assert ContentRatingPolicy.select({}, jurisdictions=BR_THEN_US) is None

    def test_should_drop_blank_labels(self):
        chosen = ContentRatingPolicy.select({"BR": "   ", "US": "R"}, jurisdictions=BR_THEN_US)

        assert chosen.minimum_age == AgeRating(17)

    def test_should_drop_blank_country_codes(self):
        chosen = ContentRatingPolicy.select({"": "R", "BR": "12"}, jurisdictions=BR_THEN_US)

        assert chosen.minimum_age == AgeRating(12)

    def test_should_return_none_when_everything_is_blank(self):
        assert ContentRatingPolicy.select({"": "  "}, jurisdictions=BR_THEN_US) is None

    def test_should_not_invent_an_age_for_an_unknown_label(self):
        chosen = ContentRatingPolicy.select({"BR": "???"}, jurisdictions=("BR",))

        assert chosen.minimum_age is None
