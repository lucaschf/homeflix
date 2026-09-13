"""ManualItemOrder — where the items of a custom list go when reordered."""

from collections.abc import Sequence

from src.modules.collections.domain.value_objects import CollectionMediaId


class ManualItemOrder:
    """Apply a client's manual order to a custom list's items.

    The client may send only part of the list: a profile under a maturity
    limit never sees — and so never sends — the titles withheld from it.
    Those items must stay where they are, or the reorder would leave two
    items claiming the same position. The rule is therefore expressed on
    slots, not on indexes into the request.
    """

    @staticmethod
    def arrange(
        current: Sequence[CollectionMediaId],
        requested: Sequence[CollectionMediaId],
    ) -> list[CollectionMediaId]:
        """Place the requested items into the slots they already occupy.

        1. ``requested`` is cleaned: repeats keep their first occurrence,
           ids that are not in the list are dropped.
        2. The slots are the places in ``current`` held by the ids that
           remain; every other item keeps its place.
        3. The remaining ids fill those slots in the order requested.

        A request that names every item exactly once yields that request
        as the new order.

        Args:
            current: The list's items in their current order. An id that
                repeats keeps only its first place.
            requested: The order the client asked for.

        Returns:
            Every distinct item of ``current``, in its new order.

        Example:
            >>> a, b, c, h1, h2 = (CollectionMediaId(f"mov_{n}00000000000") for n in "abcde")
            >>> ManualItemOrder.arrange([a, h1, b, h2, c], [c, a, b]) == [c, h1, a, h2, b]
            True
        """
        order = list(dict.fromkeys(current))
        present = set(order)
        moved = list(dict.fromkeys(media_id for media_id in requested if media_id in present))
        moving = set(moved)
        placed = iter(moved)
        return [next(placed) if media_id in moving else media_id for media_id in order]


__all__ = ["ManualItemOrder"]
