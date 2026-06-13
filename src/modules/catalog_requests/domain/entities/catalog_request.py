"""CatalogRequest aggregate root."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.building_blocks.domain import AggregateRoot
from src.modules.catalog_requests.domain.value_objects import (
    CatalogRequestId,
)
from src.shared_kernel.value_objects import (
    MediaType,  # noqa: TCH001 — runtime for Pydantic
)


class CatalogRequest(AggregateRoot[CatalogRequestId]):
    """A user-initiated request to add a TMDB title to the catalog.

    Drives the missing-from-catalog flow on the Collection Detail
    page: when a movie shown alongside a franchise isn't yet hosted,
    the user can register a request (and optionally subscribe to a
    "notify when available" prompt). Single-user platform, so
    "exists" already means "the user wants this" — no per-user
    fanout, just one row per ``(tmdb_id, media_type)``.

    The ``fulfilled_at`` timestamp closes the loop once the title is
    hosted: the read-side picks fulfilled vs. pending up via this
    field rather than re-checking the media catalog every render.

    Attributes:
        id: External ID (``req_xxx`` format).
        tmdb_id: TMDB numeric id of the requested title.
        media_type: Whether the request targets a movie or a series.
        title: Snapshot of the TMDB title at the moment the request
            was registered. The admin queue uses this to render
            "Title (tmdb/id)" inline without re-querying TMDB. May
            be ``None`` on rows created before the column existed.
        requester_user_id: External id (``usr_xxx``) of the user who
            registered the request. Layer B of the arrival flow
            uses this anchor to ping the right inbox; ``None`` on
            legacy rows skips the notification.
        collection_tmdb_id: TMDB collection id that surfaced this
            request, if any. Lets us scope listings to a single
            franchise (e.g. "all pending requests in the Alien
            Anthology").
        notify_on_arrival: ``True`` when the user has opted in to a
            notification once the title enters the catalog. Defaults
            to ``False`` — "Solicitar inclusão" alone does not
            subscribe to notifications; the user clicks "Avisar
            quando chegar" separately.
        requested_at: First-time creation timestamp. Stays put even
            if the user later flips ``notify_on_arrival``.
        fulfilled_at: Set when the title becomes available locally.
            ``None`` while the request is still pending.

    Example:
        >>> req = CatalogRequest.create(
        ...     tmdb_id=348,
        ...     media_type=MediaType.MOVIE,
        ...     title="Alien",
        ...     collection_tmdb_id=8091,
        ... )
    """

    id: CatalogRequestId | None = Field(default=None)

    tmdb_id: int
    media_type: MediaType
    title: str | None = None
    requester_user_id: str | None = None
    collection_tmdb_id: int | None = None
    notify_on_arrival: bool = False
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    fulfilled_at: datetime | None = None

    @classmethod
    def create(
        cls,
        tmdb_id: int,
        media_type: MediaType,
        title: str | None = None,
        requester_user_id: str | None = None,
        collection_tmdb_id: int | None = None,
        notify_on_arrival: bool = False,
    ) -> CatalogRequest:
        """Factory method with automatic ID generation.

        Args:
            tmdb_id: TMDB numeric id of the requested title.
            media_type: Whether the request targets a movie or a series.
            title: Snapshot of the TMDB title at request time.
                Optional — when the caller doesn't know the title
                (older clients, programmatic ingest), the field stays
                ``None`` and the admin queue falls back to the bare
                ``tmdb/<id>`` link.
            requester_user_id: External id (``usr_xxx``) of the user
                creating the request. Powers the per-user arrival
                notification; ``None`` skips the ping (legacy or
                anonymous seed).
            collection_tmdb_id: Optional franchise id that surfaced
                this request.
            notify_on_arrival: Whether to subscribe to the arrival
                notification at creation time.

        Returns:
            A new ``CatalogRequest`` instance.
        """
        return cls(
            id=CatalogRequestId.generate(),
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            requester_user_id=requester_user_id,
            collection_tmdb_id=collection_tmdb_id,
            notify_on_arrival=notify_on_arrival,
            requested_at=datetime.now(UTC),
            fulfilled_at=None,
        )

    @property
    def is_fulfilled(self) -> bool:
        """``True`` once the requested title has reached the catalog."""
        return self.fulfilled_at is not None

    def enable_notification(self) -> CatalogRequest:
        """Return a copy with ``notify_on_arrival=True``.

        Idempotent: returning the same flag value still yields a new
        copy with a refreshed ``updated_at``, which downstream layers
        ignore — but the use case short-circuits before calling this
        when the flag is already on, so no spurious writes happen.
        """
        return self.with_updates(notify_on_arrival=True)

    def reconcile(
        self,
        *,
        title: str | None = None,
        requester_user_id: str | None = None,
        notify: bool = False,
    ) -> CatalogRequest | None:
        """Fold a repeat request's data into this existing one.

        Both arrival entry points ("Solicitar inclusão" and "Avisar
        quando chegar") hit the same ``(tmdb_id, media_type)`` row on a
        re-submit and need to merge the incoming data the same way, so
        the rule lives here instead of being copied into each use case.

        First-owner-wins backfill: ``title`` and ``requester_user_id``
        are only filled when currently unset, so a later requester never
        overwrites the original owner's snapshot or reroutes their
        notification. ``notify`` is one-way — it opts the request in to
        the arrival notification but never turns an existing
        subscription off.

        Args:
            title: Candidate title snapshot from the repeat request.
            requester_user_id: Candidate requester from the repeat
                request.
            notify: Whether this entry point wants the arrival
                notification enabled.

        Returns:
            A new instance with the merged changes, or ``None`` when the
            incoming data adds nothing — letting the caller skip the
            write and return the existing row unchanged.
        """
        updates: dict[str, object] = {}
        if self.title is None and title:
            updates["title"] = title
        if self.requester_user_id is None and requester_user_id:
            updates["requester_user_id"] = requester_user_id
        if notify and not self.notify_on_arrival:
            updates["notify_on_arrival"] = True

        if not updates:
            return None
        return self.with_updates(**updates)

    def mark_fulfilled(self, fulfilled_at: datetime | None = None) -> CatalogRequest:
        """Return a copy stamped as fulfilled.

        Args:
            fulfilled_at: Override timestamp (useful in tests). Defaults
                to "now" in UTC.

        Returns:
            A new ``CatalogRequest`` with ``fulfilled_at`` populated.
        """
        return self.with_updates(fulfilled_at=fulfilled_at or datetime.now(UTC))


__all__ = ["CatalogRequest"]
