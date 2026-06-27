"""Cross-BC integration event contracts (ADR-009).

These are the stable, published shapes that bounded contexts subscribe to
across the in-process event bus. They live in ``shared_kernel`` so a
consumer never imports a producer's ``domain.events`` module.
"""

from dataclasses import dataclass, field

from src.shared_kernel.integration_events.base import IntegrationEvent
from src.shared_kernel.value_objects.media_id import EpisodeId, MovieId, SeriesId
from src.shared_kernel.value_objects.media_type import MediaType


@dataclass(frozen=True, kw_only=True)
class MediaEnrichedEvent(IntegrationEvent):
    """Emitted when an enrichment pass finishes with a known TMDB id.

    Distinct from ``MediaCreatedEvent`` because the TMDB id is only
    populated *after* enrichment runs — ``MediaCreatedEvent`` fires
    on scan with just the internal id, so a handler that needs the
    tmdb id (e.g. ``catalog_requests`` marking a pending request as
    fulfilled once the title finally lands) can't piggy-back on it.

    Fires both on the first successful enrichment and on a forced
    refresh that re-runs against TMDB. Downstream handlers should
    treat it as idempotent: re-firing on an already-fulfilled
    catalog request must short-circuit, not duplicate state.

    Also consumed in-module by ``media`` itself (the content-identity
    conflict detector), which is fine — ``media`` may import this
    shared-kernel contract like any other consumer.

    Attributes:
        media_id: External ID of the enriched media (mov_xxx or
            ser_xxx).
        media_type: :class:`MediaType` of the enriched media.
        tmdb_id: TMDB numeric id the enrichment locked onto.
    """

    media_id: MovieId | SeriesId
    media_type: MediaType
    tmdb_id: int = 0


@dataclass(frozen=True, kw_only=True)
class MovieMergedEvent(IntegrationEvent):
    """Emitted when two movies are merged via the conflict queue.

    Triggered by either the admin resolve endpoint (ADR-015 Phase 2,
    ``is_auto=False``) or the post-enrich detector silently absorbing
    an orphaned candidate (ADR-015 Phase 3, ``is_auto=True``). Carries
    the cross-BC fan-out signal: ``watch_progress`` deletes the loser's
    progress rows and ``collections`` repoints watchlist / custom-list
    items from loser → winner. The loser movie itself is already
    soft-deleted by the trigger before the event publishes, so handlers
    don't need to touch the catalog row.

    Attributes:
        conflict_id: External id of the resolved conflict (``cnf_xxx``).
        winner_id: External id of the surviving movie (``mov_xxx``).
        loser_id: External id of the soft-deleted movie (``mov_xxx``).
        keep_loser_variants: ``True`` when the resolution was
            ``MERGE_KEEP_BOTH`` — the loser's file variants were
            transferred to the winner; cross-BC handlers can treat
            this identically to ``MERGE_REPLACE`` (rows still need to
            be repointed). Surfaced for analytics / audit.
        is_auto: ``True`` when the merge was decided by the auto-merge
            path (orphan + healthy library), ``False`` when an admin
            picked the resolution. Cross-BC handlers apply the same
            fan-out either way; the flag is surfaced for logs and
            audit reports.
    """

    conflict_id: str = ""
    winner_id: MovieId
    loser_id: MovieId
    keep_loser_variants: bool = False
    is_auto: bool = False


@dataclass(frozen=True, kw_only=True)
class MoviePromotedToSeriesEvent(IntegrationEvent):
    """Emitted when an admin promotes a movie into a series.

    Driven by the cross-type relink flow (e.g. ``Salem's Lot (1979)``,
    which TMDB catalogs as a TV miniseries rather than a film).

    The original movie row is soft-deleted; a new series + season
    + episodes structure takes its place. All file variants of the
    movie are reattached to the first episode (``first_episode_id``)
    so external bounded contexts know where playback state should
    migrate (or — per the agreed design — where to delete it).

    Cross-BC handlers:
        - ``watch_progress`` deletes WatchProgress rows for the old
          movie id (safer than mapping a position across a possibly
          re-cut episode boundary).
        - ``collections`` rewrites watchlist + custom-list entries
          to point at the new series id.

    Attributes:
        movie_id: External ID of the source movie (mov_xxx).
        series_id: External ID of the new series (ser_xxx).
        first_episode_id: External ID of the first episode (epi_xxx)
            that now owns the movie's file variants.
    """

    movie_id: MovieId
    series_id: SeriesId
    first_episode_id: EpisodeId


@dataclass(frozen=True)
class UserDeletedEvent(IntegrationEvent):
    """Emitted when an admin soft-deletes a user account.

    Carries the full list of profile ids owned by the deleted user
    so downstream bounded contexts can cascade their per-profile
    state without re-querying identity (which would race against the
    soft-delete tombstone). Profile ids are passed by-value because
    cross-BC FKs are forbidden by ADR-008.

    Cross-BC handlers:
        - ``watch_progress`` soft-deletes every ``watch_progresses``
          row whose ``profile_id`` matches one of the deleted user's
          profiles. The half-watched position belongs to that
          person; restoring it later would be a privacy footgun.
        - ``collections`` soft-deletes the user's watchlists and
          custom lists (lists belong to profiles, not users) so the
          ex-user's library state isn't visible to anyone else.

    Both handlers run fire-and-forget on the event bus — failures
    are logged but the user-delete still commits. Operators can
    re-run the cleanup later if a downstream BC was offline.

    Attributes:
        user_id: External ID of the deleted user (usr_xxx).
        profile_ids: External IDs of every profile the user owned
            at deletion time (pro_xxx). May be empty if the user
            never created a profile.
    """

    user_id: str = ""
    profile_ids: tuple[str, ...] = field(default_factory=tuple)


__all__ = [
    "MediaEnrichedEvent",
    "MovieMergedEvent",
    "MoviePromotedToSeriesEvent",
    "UserDeletedEvent",
]
