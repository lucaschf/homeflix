"""Tests for certification-label normalization (ADR-035).

The census in :data:`REAL_MOVIE_CENSUS` / :data:`REAL_SERIES_CENSUS` is
the actual label distribution of the running library, measured on
2026-09-12. It is here so the table is tested against the labels that
exist rather than the ones a table author imagines, and so the headline
figures the decision rested on ("a profile limited to 12 sees 173
movies") stay honest as the table changes.

It counts **live** rows only (``deleted_at IS NULL``). A soft-deleted
title is invisible to every query, so counting one would overstate what
a profile actually sees.
"""

import pytest

from src.shared_kernel.content_policy import classify, strictest
from src.shared_kernel.value_objects import AgeRating, ContentRating, RatingSystem

# label -> (title count, expected minimum age or None) for 644 live movies
REAL_MOVIE_CENSUS: list[tuple[str | None, int, int | None]] = [
    ("R", 128, 17),
    ("14", 98, 14),
    ("L", 88, 0),
    (None, 73, None),
    ("16", 70, 16),
    ("12", 62, 12),
    ("PG", 28, 13),
    ("NR", 27, None),
    ("18", 24, 18),
    ("PG-13", 23, 13),
    ("10", 19, 10),
    ("G", 4, 0),
]

# label -> (title count, expected minimum age or None) for 57 live series
REAL_SERIES_CENSUS: list[tuple[str | None, int, int | None]] = [
    ("L", 17, 0),
    ("12", 12, 12),
    ("14", 9, 14),
    ("16", 6, 16),
    ("10", 6, 10),
    ("18", 2, 18),
    (None, 2, None),
    ("TV-Y7", 1, 7),
    ("TV-MA", 1, 17),
    ("TV-14", 1, 14),
]


def _visible(census: list[tuple[str | None, int, int | None]], limit: int) -> int:
    """Count titles a profile limited to ``limit`` would see."""
    ceiling = AgeRating(limit)
    return sum(
        count
        for label, count, _ in census
        if ceiling.allows(classify(label).minimum_age if label is not None else None)
    )


class TestBrazilianScale:
    """Classificação Indicativa — the bulk of the real catalog."""

    @pytest.mark.parametrize(
        ("label", "age"),
        [
            ("L", 0),
            ("Livre", 0),
            ("AL", 0),
            ("10", 10),
            ("12", 12),
            ("14", 14),
            ("16", 16),
            ("18", 18),
        ],
    )
    def test_should_map_label_to_age(self, label, age):
        assert classify(label, country="BR").minimum_age == AgeRating(age)

    @pytest.mark.parametrize(("label", "age"), [("A10", 10), ("A12", 12), ("A14", 14), ("A16", 16)])
    def test_should_accept_prefixed_spelling(self, label, age):
        assert classify(label, country="BR").minimum_age == AgeRating(age)

    def test_should_attribute_bare_number_to_brazil_when_country_known(self):
        assert classify("12", country="BR").system is RatingSystem.BR_DEJUS

    def test_should_fall_back_to_generic_numeric_without_country(self):
        cert = classify("12")

        assert cert.system is RatingSystem.NUMERIC
        assert cert.minimum_age == AgeRating(12)


class TestMpaScale:
    """MPA film ratings, including the deliberate PG reading."""

    @pytest.mark.parametrize(
        ("label", "age"),
        [("G", 0), ("PG", 13), ("PG-13", 13), ("PG13", 13), ("R", 17), ("NC-17", 18), ("NC17", 18)],
    )
    def test_should_map_label_to_age(self, label, age):
        cert = classify(label, country="US")

        assert cert.system is RatingSystem.US_MPA
        assert cert.minimum_age == AgeRating(age)

    def test_should_read_pg_as_thirteen_not_ten(self):
        """ADR-035: ambiguous PG takes the stricter reading — pre-1984 PG absorbed PG-13."""
        assert classify("PG").minimum_age == AgeRating(13)
        assert AgeRating(12).allows(classify("PG").minimum_age) is False


class TestTelevisionScale:
    """US TV parental guidelines."""

    @pytest.mark.parametrize(
        ("label", "age"),
        [
            ("TV-Y", 0),
            ("TV-Y7", 7),
            ("TV-Y7-FV", 7),
            ("TV-G", 0),
            ("TV-PG", 10),
            ("TV-14", 14),
            ("TV-MA", 17),
        ],
    )
    def test_should_map_label_to_age(self, label, age):
        cert = classify(label)

        assert cert.system is RatingSystem.US_TV
        assert cert.minimum_age == AgeRating(age)


class TestNumericScale:
    """Scales whose label already is the age."""

    @pytest.mark.parametrize(
        ("label", "age"), [("0+", 0), ("6", 6), ("15", 15), ("16+", 16), ("18", 18)]
    )
    def test_should_read_the_number(self, label, age):
        assert classify(label).minimum_age == AgeRating(age)

    def test_should_clamp_nonsensical_number_to_ceiling(self):
        """Discarding it would resolve to adult (18) — less strict than the label claims."""
        assert classify("99").minimum_age == AgeRating(AgeRating.MAX)


class TestUndeterminedLabels:
    """The fail-closed path — the decision that makes or breaks the feature."""

    @pytest.mark.parametrize("label", ["NR", "UR", "N/A", "NA", "Unrated", "Not Rated", "-"])
    def test_should_not_derive_an_age(self, label):
        cert = classify(label)

        assert cert.minimum_age is None
        assert cert.is_determined is False

    @pytest.mark.parametrize("label", ["M/16", "Banned", "???", "VM14"])
    def test_should_not_guess_an_unknown_label(self, label):
        cert = classify(label)

        assert cert.minimum_age is None
        assert cert.system is RatingSystem.UNKNOWN

    def test_should_preserve_the_original_label_for_display(self):
        assert classify("NR").label == ContentRating("NR")

    @pytest.mark.parametrize(
        "label",
        [
            "Genel Izleyici Kitlesi",  # the real Turkish board label, 22 chars
            "No recomendada para menores de dieciocho anos",
            "x" * 21,
        ],
    )
    def test_should_return_none_for_a_label_too_long_to_store(self, label):
        """TMDB certifications are contributor-entered free text.

        A board that writes prose must not blow up the caller — one
        foreign label would abort the whole enrichment of a title.
        ``None`` is distinct from unrated: there is no label to keep.
        """
        assert classify(label) is None

    def test_should_still_classify_a_label_at_the_length_limit(self):
        assert classify("x" * 20) is not None

    def test_should_never_map_an_unknown_label_to_zero(self):
        """The silent failure this table exists to avoid."""
        for label in ("NR", "UR", "Banned", "???"):
            assert classify(label).minimum_age != AgeRating(0)


class TestNormalization:
    """Input hygiene — providers and operators are not consistent."""

    @pytest.mark.parametrize("label", ["pg-13", "PG-13", " pg-13 ", "Pg-13"])
    def test_should_be_case_and_whitespace_insensitive(self, label):
        assert classify(label).minimum_age == AgeRating(13)

    def test_should_collapse_internal_whitespace(self):
        assert classify("Not   Rated").is_determined is False

    def test_should_accept_a_content_rating_instance(self):
        cert = classify(ContentRating("TV-MA"))

        assert cert.minimum_age == AgeRating(17)
        assert cert.label == ContentRating("TV-MA")

    def test_should_keep_label_verbatim_not_canonicalized(self):
        """The badge shows what the provider emitted, not what the table matched on."""
        assert classify("pg-13").label == ContentRating("pg-13")


class TestStrictest:
    """Tie-breaker across jurisdictions."""

    def test_should_pick_the_highest_age(self):
        candidates = [classify("12", country="BR"), classify("R", country="US")]

        assert strictest(candidates).minimum_age == AgeRating(17)

    def test_should_ignore_undetermined_candidates(self):
        candidates = [classify("NR"), classify("10", country="BR")]

        assert strictest(candidates).minimum_age == AgeRating(10)

    def test_should_return_none_when_nothing_is_determined(self):
        assert strictest([classify("NR"), classify("???")]) is None

    def test_should_return_none_for_empty_input(self):
        assert strictest([]) is None


class TestAgainstRealCatalog:
    """Every label that exists in the running library, and what the ladder yields."""

    @pytest.mark.parametrize(("label", "count", "age"), REAL_MOVIE_CENSUS)
    def test_should_classify_every_movie_label_in_use(self, label, count, age):
        if label is None:
            pytest.skip("absent rating is modelled as None, not as a label")

        expected = None if age is None else AgeRating(age)
        assert classify(label).minimum_age == expected

    @pytest.mark.parametrize(("label", "count", "age"), REAL_SERIES_CENSUS)
    def test_should_classify_every_series_label_in_use(self, label, count, age):
        if label is None:
            pytest.skip("absent rating is modelled as None, not as a label")

        expected = None if age is None else AgeRating(age)
        assert classify(label).minimum_age == expected

    def test_census_totals_match_the_measured_library(self):
        assert sum(count for _, count, _ in REAL_MOVIE_CENSUS) == 644
        assert sum(count for _, count, _ in REAL_SERIES_CENSUS) == 57

    @pytest.mark.parametrize(
        ("limit", "movies", "series"),
        [
            (0, 92, 17),
            (10, 111, 24),
            (12, 173, 36),
            (14, 322, 46),
            (16, 392, 52),
            (18, 644, 57),
        ],
    )
    def test_ladder_step_yields_the_documented_catalog_size(self, limit, movies, series):
        """The figures ADR-035 rests on. A table change that moves these is a decision, not a refactor."""
        assert _visible(REAL_MOVIE_CENSUS, limit) == movies
        assert _visible(REAL_SERIES_CENSUS, limit) == series

    def test_unrestricted_profile_sees_everything(self):
        assert _visible(REAL_MOVIE_CENSUS, AgeRating.ADULT) == 644

    def test_limited_profile_never_sees_the_unrated_tail(self):
        """100 movies (73 without a label + 27 NR) stay hidden from every limited profile."""
        assert _visible(REAL_MOVIE_CENSUS, 17) == 644 - 100 - 24
