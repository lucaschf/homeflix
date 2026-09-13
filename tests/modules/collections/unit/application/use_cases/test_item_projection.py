"""Tests for the shared custom-list item projection (``project_items``).

The projection is where every list read applies the caller's viewing
policy, so these tests pin the order of its checks: a removed title is
not counted, a title outside the caller's libraries is counted in
``hidden_count`` whatever its age, and a title above the maturity limit
is dropped without being counted anywhere a response can show.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_media_lookup_mock,
    make_progress_lookup_mock,
)

from src.modules.collections.application.use_cases._item_projection import (
    ProjectedItems,
    permits_summary,
    project_items,
)
from src.modules.collections.domain.entities import CustomListItem
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.library_id import LibraryId

if TYPE_CHECKING:
    from tests.modules.collections.unit.application.use_cases.conftest import (
        MediaSummaryFactory,
    )

    from src.modules.collections.application.ports import MediaSummary

_PROFILE_ID = "prf_test12345678"
_LIB_A = "lib_libraryaaaa1"
_LIB_B = "lib_librarybbbb1"

_LIMITED = ViewingPolicy(allowed_library_ids=[_LIB_A], maturity_limit=AgeRating(12))
_LIBRARY_ONLY = ViewingPolicy.unrestricted([_LIB_A])

#: Seeded ages: ``(id fragment, minimum age)``; ``None`` is an unrated title.
_AGES: list[tuple[str, AgeRating | None]] = [
    ("ten", AgeRating(10)),
    ("sixteen", AgeRating(16)),
    ("unrated", None),
]
_REMOVED = "removed"


def _media_id(library_id: str, shape: str) -> str:
    """A 12-character movie id naming the seeded library and shape."""
    return f"mov_{library_id[-5:]}{shape[:7]:x<7}"


def _item(media_id: str, position: int) -> CustomListItem:
    return CustomListItem.create(media_id=media_id, media_type=MediaType.MOVIE, position=position)


async def _project(
    items: list[CustomListItem],
    summaries: list[MediaSummary],
    policy: ViewingPolicy,
) -> ProjectedItems:
    return await project_items(
        items,
        media_lookup=make_media_lookup_mock(*summaries),
        progress_lookup=make_progress_lookup_mock(),
        lang="en",
        profile_id=_PROFILE_ID,
        policy=policy,
    )


def _matrix(
    movie_summary: MediaSummaryFactory,
) -> tuple[list[CustomListItem], list[MediaSummary]]:
    """Every library crossed with {10, 16, unrated, removed}, in list order."""
    items: list[CustomListItem] = []
    summaries: list[MediaSummary] = []
    for library_id in (_LIB_A, _LIB_B):
        for shape, age in _AGES:
            media_id = _media_id(library_id, shape)
            items.append(_item(media_id, position=len(items)))
            summaries.append(movie_summary(media_id, library_id=library_id, minimum_age=age))
        items.append(_item(_media_id(library_id, _REMOVED), position=len(items)))
    return items, summaries


def _ids(projected: ProjectedItems) -> list[str]:
    return [output.media_id for output in projected.items]


@pytest.mark.unit
class TestProjectItemsAxes:
    """Which items are emitted, counted as hidden, or withheld."""

    @pytest.mark.asyncio
    async def test_emits_exactly_what_the_policy_permits(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        items, summaries = _matrix(movie_summary)
        by_id = {summary.media_id: summary for summary in summaries}

        projected = await _project(items, summaries, _LIMITED)

        expected = [
            item.media_id.value
            for item in items
            if item.media_id.value in by_id
            and _LIMITED.permits(
                library_id=LibraryId(by_id[item.media_id.value].library_id),
                minimum_age=by_id[item.media_id.value].minimum_age,
            )
        ]
        assert _ids(projected) == expected == [_media_id(_LIB_A, "ten")]

    @pytest.mark.asyncio
    async def test_hidden_count_is_the_library_axis_only(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        items, summaries = _matrix(movie_summary)

        limited = await _project(items, summaries, _LIMITED)
        library_only = await _project(items, summaries, _LIBRARY_ONLY)

        # Every resolvable title in library B counts — the one rated 16
        # included, because the library check comes first.
        assert limited.hidden_count == library_only.hidden_count == 3
        assert limited.withheld_by_maturity == 2
        assert library_only.withheld_by_maturity == 0

    @pytest.mark.asyncio
    async def test_title_outside_the_libraries_and_above_the_limit_counts_as_hidden(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        media_id = _media_id(_LIB_B, "sixteen")

        projected = await _project(
            [_item(media_id, 0)],
            [movie_summary(media_id, library_id=_LIB_B, minimum_age=AgeRating(16))],
            _LIMITED,
        )

        assert projected.items == []
        assert projected.hidden_count == 1
        assert projected.withheld_by_maturity == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("policy", [_LIMITED, _LIBRARY_ONLY], ids=["limited", "library-only"])
    async def test_removed_title_is_not_counted(self, policy: ViewingPolicy) -> None:
        items = [
            _item(_media_id(library_id, _REMOVED), i)
            for i, library_id in enumerate((_LIB_A, _LIB_B))
        ]

        projected = await _project(items, [], policy)

        assert projected == ProjectedItems(items=[], hidden_count=0, withheld_by_maturity=0)

    @pytest.mark.asyncio
    async def test_all_ages_rating_is_a_rating_and_unrated_reads_as_adult(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        free = _media_id(_LIB_A, "livre")
        unrated = _media_id(_LIB_A, "unrated")
        items = [_item(free, 0), _item(unrated, 1)]
        summaries = [
            movie_summary(free, library_id=_LIB_A, minimum_age=AgeRating(0)),
            movie_summary(unrated, library_id=_LIB_A, minimum_age=None),
        ]
        adult = ViewingPolicy(allowed_library_ids=[_LIB_A], maturity_limit=AgeRating(18))

        under_twelve = await _project(items, summaries, _LIMITED)
        under_eighteen = await _project(items, summaries, adult)

        assert _ids(under_twelve) == [free]
        assert under_twelve.withheld_by_maturity == 1
        assert _ids(under_eighteen) == [free, unrated]
        assert under_eighteen.withheld_by_maturity == 0


@pytest.mark.unit
class TestProjectItemsPositions:
    """Positions are renumbered only under a maturity limit."""

    @pytest.mark.asyncio
    async def test_positions_are_contiguous_under_a_maturity_limit(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        ids = [_media_id(_LIB_A, f"pos{n}") for n in range(5)]
        ages = [AgeRating(10), AgeRating(16), AgeRating(10), None, AgeRating(12)]
        items = [
            _item(media_id, position)
            for media_id, position in zip(ids, (0, 2, 3, 7, 9), strict=True)
        ]
        summaries = [
            movie_summary(media_id, library_id=_LIB_A, minimum_age=age)
            for media_id, age in zip(ids, ages, strict=True)
        ]

        projected = await _project(items, summaries, _LIMITED)

        assert _ids(projected) == [ids[0], ids[2], ids[4]]
        assert [output.position for output in projected.items] == [0, 1, 2]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("stored", "ages", "expected_positions", "withheld"),
        [
            pytest.param(
                (2, 5, 9),
                (AgeRating(10), AgeRating(0), AgeRating(12)),
                [0, 1, 2],
                0,
                id="nothing-withheld",
            ),
            pytest.param(
                (3, 4, 8),
                (AgeRating(10), AgeRating(0), AgeRating(16)),
                [0, 1],
                1,
                id="only-last-withheld",
            ),
        ],
    )
    async def test_positions_are_renumbered_under_a_limit_before_anything_is_withheld(
        self,
        movie_summary: MediaSummaryFactory,
        stored: tuple[int, ...],
        ages: tuple[AgeRating, ...],
        expected_positions: list[int],
        withheld: int,
    ) -> None:
        ids = [_media_id(_LIB_A, f"pos{n}") for n in range(len(stored))]
        items = [_item(media_id, position) for media_id, position in zip(ids, stored, strict=True)]
        summaries = [
            movie_summary(media_id, library_id=_LIB_A, minimum_age=age)
            for media_id, age in zip(ids, ages, strict=True)
        ]

        projected = await _project(items, summaries, _LIMITED)

        assert [output.position for output in projected.items] == expected_positions
        assert projected.withheld_by_maturity == withheld

    @pytest.mark.asyncio
    async def test_stored_positions_are_kept_without_a_maturity_limit(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        ids = [_media_id(_LIB_A, f"pos{n}") for n in range(3)]
        stored = (0, 2, 7)
        items = [_item(media_id, position) for media_id, position in zip(ids, stored, strict=True)]
        summaries = [
            movie_summary(ids[0], library_id=_LIB_A),
            movie_summary(ids[1], library_id=_LIB_B),
            movie_summary(ids[2], library_id=_LIB_A, minimum_age=AgeRating(18)),
        ]

        projected = await _project(items, summaries, _LIBRARY_ONLY)

        assert _ids(projected) == [ids[0], ids[2]]
        assert [output.position for output in projected.items] == [0, 7]


@pytest.mark.unit
class TestPermitsSummary:
    """The both-axes rule the watchlist read applies per item."""

    @pytest.mark.parametrize(
        ("library_id", "minimum_age", "limit", "expected"),
        [
            pytest.param(_LIB_A, AgeRating(10), AgeRating(12), True, id="within"),
            pytest.param(_LIB_A, AgeRating(16), AgeRating(12), False, id="above-limit"),
            pytest.param(_LIB_B, AgeRating(10), AgeRating(12), False, id="other-library"),
            pytest.param(_LIB_A, AgeRating(0), AgeRating(12), True, id="all-ages"),
            pytest.param(_LIB_A, None, AgeRating(12), False, id="unrated-under-12"),
            pytest.param(_LIB_A, None, AgeRating(18), True, id="unrated-under-18"),
            pytest.param(_LIB_A, None, None, True, id="unrated-no-limit"),
            pytest.param(None, AgeRating(10), None, False, id="unknown-library"),
        ],
    )
    def test_both_axes(
        self,
        movie_summary: MediaSummaryFactory,
        library_id: str | None,
        minimum_age: AgeRating | None,
        limit: AgeRating | None,
        expected: bool,
    ) -> None:
        policy = ViewingPolicy(allowed_library_ids=[_LIB_A], maturity_limit=limit)
        summary = movie_summary(
            _media_id(_LIB_A, "any"), library_id=library_id, minimum_age=minimum_age
        )

        assert permits_summary(policy, summary) is expected
