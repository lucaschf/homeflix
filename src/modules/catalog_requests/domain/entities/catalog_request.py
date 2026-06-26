"""CatalogRequest aggregate root."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.building_blocks.domain import AggregateRoot
from src.modules.catalog_requests.domain.value_objects import (
    CatalogRequestId,
    CatalogRequestSource,
    CatalogRequestStatus,
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
        source: Where the request originated — :attr:`USER` when a
            member asked for it, :attr:`HOUSEHOLD` when the system
            seeded it (ADR-022). Derived from ``requester_user_id`` at
            creation and fixed thereafter. See also the derived
            :attr:`status` property (pending vs. fulfilled).
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
    # Per-language title snapshot built once at request creation from
    # TMDB (``{lang: title}``). ``get_title(lang)`` reads this so the
    # "Em breve" feed renders in the viewer's language; falls back to
    # the English snapshot / ``title`` when a locale is missing.
    localized_titles: dict[str, str] = Field(default_factory=dict)
    poster_url: str | None = None
    requester_user_id: str | None = None
    collection_tmdb_id: int | None = None
    source: CatalogRequestSource = CatalogRequestSource.HOUSEHOLD
    notify_on_arrival: bool = False
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    fulfilled_at: datetime | None = None

    @classmethod
    def create(
        cls,
        tmdb_id: int,
        media_type: MediaType,
        title: str | None = None,
        poster_url: str | None = None,
        requester_user_id: str | None = None,
        collection_tmdb_id: int | None = None,
        notify_on_arrival: bool = False,
        localized_titles: dict[str, str] | None = None,
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
            localized_titles: Per-language title snapshot ``{lang:
                title}`` resolved once from TMDB at creation. Empty
                when TMDB was unreachable; ``get_title`` then falls
                back to ``title``.
            poster_url: Snapshot of the TMDB poster URL at request
                time, for the "Em breve" grid. ``None`` when unknown.
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
            localized_titles=localized_titles or {},
            poster_url=poster_url,
            requester_user_id=requester_user_id,
            collection_tmdb_id=collection_tmdb_id,
            source=CatalogRequestSource.for_requester(requester_user_id),
            notify_on_arrival=notify_on_arrival,
            requested_at=datetime.now(UTC),
            fulfilled_at=None,
        )

    def get_title(self, lang: str = "en") -> str | None:
        """Title in the requested language, falling back to the snapshot.

        Resolution order: the requested locale's TMDB snapshot, then
        the English snapshot, then the raw ``title`` the client sent at
        request time (or ``None`` for legacy/programmatic rows).
        """
        return self.localized_titles.get(lang) or self.localized_titles.get("en") or self.title

    @property
    def is_fulfilled(self) -> bool:
        """``True`` once the requested title has reached the catalog."""
        return self.fulfilled_at is not None

    @property
    def status(self) -> CatalogRequestStatus:
        """Honest, derived status (pending vs. fulfilled) — never stored."""
        return CatalogRequestStatus.FULFILLED if self.is_fulfilled else CatalogRequestStatus.PENDING

    def enable_notification(self) -> CatalogRequest:
        """Return a copy with ``notify_on_arrival=True``.

        Idempotent: returning the same flag value still yields a new
        copy with a refreshed ``updated_at``, which downstream layers
        ignore — but the use case short-circuits before calling this
        when the flag is already on, so no spurious writes happen.
        """
        return self.with_updates(notify_on_arrival=True)

    def disable_notification(self) -> CatalogRequest:
        """Return a copy with ``notify_on_arrival=False``.

        The mirror of :meth:`enable_notification`. Since ADR-022 the
        flag is a denormalized "has at least one active subscriber"
        cache (the precise fanout list lives in ``CatalogSubscription``
        rows): the unsubscribe use case calls this once the last
        subscriber drops off so the read-side CTA flips back to
        "Avisar quando chegar".
        """
        return self.with_updates(notify_on_arrival=False)

    def reconcile(
        self,
        *,
        title: str | None = None,
        poster_url: str | None = None,
        requester_user_id: str | None = None,
        notify: bool = False,
        localized_titles: dict[str, str] | None = None,
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
            poster_url: Candidate poster URL from the repeat request.
            requester_user_id: Candidate requester from the repeat
                request.
            notify: Whether this entry point wants the arrival
                notification enabled.
            localized_titles: Per-language title snapshot to backfill
                when the existing row has none yet (first-owner-wins,
                same as ``title``).

        Returns:
            A new instance with the merged changes, or ``None`` when the
            incoming data adds nothing — letting the caller skip the
            write and return the existing row unchanged.
        """
        updates: dict[str, object] = {}
        if self.title is None and title:
            updates["title"] = title
        if not self.localized_titles and localized_titles:
            updates["localized_titles"] = localized_titles
        if self.poster_url is None and poster_url:
            updates["poster_url"] = poster_url
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
