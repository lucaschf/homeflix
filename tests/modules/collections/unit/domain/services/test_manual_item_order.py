"""Tests for the ManualItemOrder domain service."""

import pytest

from src.modules.collections.domain.services import ManualItemOrder
from src.modules.collections.domain.value_objects import CollectionMediaId

A = CollectionMediaId("mov_aaaaaaaaaaaa")
B = CollectionMediaId("mov_bbbbbbbbbbbb")
C = CollectionMediaId("ser_cccccccccccc")
H1 = CollectionMediaId("mov_hidden000001")
H2 = CollectionMediaId("ser_hidden000002")
UNKNOWN = CollectionMediaId("mov_unknown00001")


@pytest.mark.unit
class TestManualItemOrderArrange:
    """``arrange`` places the requested items into their own slots."""

    def test_should_keep_unsent_items_in_their_slots(self) -> None:
        assert ManualItemOrder.arrange([A, H1, B, H2, C], [C, A, B]) == [C, H1, A, H2, B]

    def test_should_follow_a_request_naming_every_item(self) -> None:
        assert ManualItemOrder.arrange([A, H1, B, H2, C], [H2, C, A, H1, B]) == [
            H2,
            C,
            A,
            H1,
            B,
        ]

    def test_should_ignore_unknown_and_repeated_ids_without_shifting_slots(self) -> None:
        # Slots of C and A are 0 and 4; the unknown id and the second C
        # must not take one of them.
        assert ManualItemOrder.arrange([A, H1, B, H2, C], [UNKNOWN, C, C, A]) == [
            C,
            H1,
            B,
            H2,
            A,
        ]

    def test_should_leave_the_order_alone_for_an_empty_or_foreign_request(self) -> None:
        assert ManualItemOrder.arrange([A, H1, B], []) == [A, H1, B]
        assert ManualItemOrder.arrange([A, H1, B], [UNKNOWN]) == [A, H1, B]

    def test_should_keep_a_repeated_current_item_once_at_its_first_place(self) -> None:
        assert ManualItemOrder.arrange([A, B, A, C], [C, A]) == [C, B, A]

    def test_should_return_every_item_exactly_once(self) -> None:
        current = [A, H1, B, H2, C]

        arranged = ManualItemOrder.arrange(current, [B, UNKNOWN, B, A])

        assert sorted(arranged, key=str) == sorted(current, key=str)
        assert len(set(arranged)) == len(arranged)
