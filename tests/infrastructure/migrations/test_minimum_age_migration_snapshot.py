"""Guards the frozen rating-scale snapshot inside the minimum-age migration.

The migration deliberately carries its own copy of the label-to-age
table so replaying history stays deterministic (see its module
docstring). A copy nobody checks is a copy that rots, so this test holds
the snapshot against the live table and fails the moment they disagree.

A failure here is not a bug to paper over. It means the live scale
changed, and there are exactly two correct responses:

1. The change should apply to rows already in the database — write a new
   data migration that re-derives them, and update this snapshot.
2. The change should apply only to titles enriched from now on — update
   this snapshot alone.

Silently editing the migration to import the live table is the one
option that is always wrong.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from src.shared_kernel.content_policy import UNRATED_LABELS, classify

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "2026_09_12_add_minimum_age_to_catalog.py"
)
_spec = importlib.util.spec_from_file_location("_minimum_age_migration", _MIGRATION_PATH)
if _spec is None or _spec.loader is None:
    msg = f"Could not load migration at {_MIGRATION_PATH}"
    raise RuntimeError(msg)
_MIGRATION = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _MIGRATION
_spec.loader.exec_module(_MIGRATION)


class TestSnapshotMatchesLiveScale:
    """Every label in the snapshot must still normalize the same way."""

    @pytest.mark.parametrize("label", sorted(_MIGRATION.SCALE_SNAPSHOT))
    def test_snapshot_label_agrees_with_live_table(self, label):
        expected_system, expected_age = _MIGRATION.SCALE_SNAPSHOT[label]
        live = classify(label)

        assert live.minimum_age is not None, f"{label} no longer yields an age"
        assert (
            live.minimum_age.value == expected_age
        ), f"{label}: snapshot says {expected_age}, live table says {live.minimum_age.value}"
        assert live.system.value == expected_system

    def test_unrated_labels_agree(self):
        assert _MIGRATION.UNRATED_SNAPSHOT == UNRATED_LABELS

    def test_live_table_has_no_label_the_snapshot_lacks(self):
        """A new label in the live table means already-stored rows may need back-filling.

        Reads the private ``_SCALES`` registry rather than naming the
        individual scale constants: a whole new system (say German FSK)
        registered there would be invisible to a test that lists the
        three scales it happens to know about, and titles already stored
        with those labels would sit at ``minimum_age IS NULL`` forever
        with nothing to flag the missing back-fill.
        """
        from src.shared_kernel.content_policy.certification_scale import _SCALES

        live_labels = set().union(*(set(scale) for scale in _SCALES.values()))
        # Bare numerals are handled by the numeric branch in both places,
        # so they are intentionally absent from the snapshot's table.
        live_labels = {label for label in live_labels if not label.isdigit()}

        assert live_labels == set(_MIGRATION.SCALE_SNAPSHOT)

    def test_every_registered_scale_is_reachable_without_a_country(self):
        """A scale in ``_SCALES`` but missing from ``_LOOKUP_ORDER`` is dead code.

        ``classify`` walks ``_LOOKUP_ORDER`` when no country is given —
        which is the path the back-fill takes, since stored rows do not
        record their jurisdiction.
        """
        from src.shared_kernel.content_policy.certification_scale import (
            _LOOKUP_ORDER,
            _SCALES,
        )

        assert set(_SCALES) == set(_LOOKUP_ORDER)


class TestDeriveMatchesClassify:
    """The migration's helper must agree with ``classify`` on real input."""

    @pytest.mark.parametrize(
        "label",
        [
            # every label present in the measured library
            "R",
            "14",
            "L",
            "16",
            "12",
            "PG",
            "NR",
            "PG-13",
            "18",
            "10",
            "G",
            "TV-Y7",
            "TV-MA",
            "TV-14",
            # plus the shapes the helper has to survive
            "  pg-13  ",
            "16+",
            "0+",
            "99",
            "Not Rated",
            "M/16",
            "???",
            "",
        ],
    )
    def test_derived_age_matches_the_live_table(self, label):
        derived = _MIGRATION._derive(label)
        live = classify(label).minimum_age if label.strip() else None

        if derived is None:
            assert live is None, f"{label!r}: migration skips it but the live table gives {live}"
        else:
            assert live is not None
            assert derived[1] == live.value

    def test_never_derives_zero_for_an_unrated_label(self):
        """The fail-closed rule has to hold in the migration too."""
        for label in ("NR", "UR", "Not Rated", "???", "M/16"):
            assert _MIGRATION._derive(label) is None


class TestBackfillCoverage:
    """What the back-fill would produce for the measured library."""

    def test_expected_coverage_of_the_real_catalog(self):
        """571 labelled live movies minus 27 NR leaves 544 with an age; all 55 series resolve.

        Counts **live** rows only, matching the back-fill's
        ``deleted_at IS NULL`` scope. Three soft-deleted movies carry
        derivable labels and are deliberately left alone: they are
        invisible to every query, and updating them would fire the FTS5
        triggers for rows that are not in the index.
        """
        movie_census = {
            "R": 128,
            "14": 98,
            "L": 88,
            "16": 70,
            "12": 62,
            "PG": 28,
            "NR": 27,
            "18": 24,
            "PG-13": 23,
            "10": 19,
            "G": 4,
        }
        series_census = {
            "L": 17,
            "12": 12,
            "14": 9,
            "16": 6,
            "10": 6,
            "18": 2,
            "TV-Y7": 1,
            "TV-MA": 1,
            "TV-14": 1,
        }

        def with_age(census):
            return sum(n for label, n in census.items() if _MIGRATION._derive(label) is not None)

        assert with_age(movie_census) == 544
        assert with_age(series_census) == 55
