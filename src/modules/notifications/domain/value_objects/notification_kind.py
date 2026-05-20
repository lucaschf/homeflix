"""Kinds of in-app notifications."""

from enum import StrEnum


class NotificationKind(StrEnum):
    """Discriminator for in-app notifications.

    The frontend dispatches on this value to pick the right icon,
    the right click-through (e.g. a fulfilled catalog request
    deep-links to the new title's detail page), and the right
    copy under the household's locale. New kinds land additively
    so old rows in the DB keep rendering through the legacy
    handler until they're either read or aged out.

    Example:
        >>> NotificationKind.CATALOG_REQUEST_FULFILLED
        <NotificationKind.CATALOG_REQUEST_FULFILLED: 'catalog_request_fulfilled'>
    """

    CATALOG_REQUEST_FULFILLED = "catalog_request_fulfilled"


__all__ = ["NotificationKind"]
