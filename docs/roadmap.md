# HomeFlix — Roadmap

> Last updated: 2026-08-16

This roadmap captures **what comes next** after the Phase 1 foundation.
Items are ordered so each tier builds on the previous one — both in
infrastructure (later items reuse plumbing from earlier ones) and in
the architectural patterns they exercise.

The guiding principle: HomeFlix is a **learning lab** first and a
**personal tool** second. Features are selected when they score high
on at least one axis — ideally both. Features that would turn the
project into a feature-replication exercise without teaching new
patterns are explicitly excluded.

---

## Shipped (Phases 1–4 + ADR-015 Phases 1–4 + 6.5 + Phase 7 / ADR-016–031)

### Phase 1 — Foundation

- Media catalog (Movie, Series, Season, Episode) with Clean Architecture
- Library CRUD with metadata provider config and scan settings
- HLS streaming with FFmpeg (multi-audio, multi-subtitle, resume)
- Watch progress tracking and "Continue Watching"
- Collections (Watchlist + Custom Lists up to 10)
- Playback preferences API (audio/subtitle lang, mode, quality, speed)
- Full-text search (FTS5 with BM25 ranking)
- Genre browsing with cursor pagination
- TMDB metadata enrichment (single + bulk)
- Media file variants (multiple resolutions per media)
- Catalog requests (mark missing titles for arrival)
- Responsive React frontend with MUI, TanStack Query, hls.js player
- i18n (pt-BR + en)

### Phase 2 — Hardening (partial)

- **2.3 Scheduled Scan / Background Jobs** — APScheduler-based
  scheduler with library scan, thumbnail backfill, intro detection
  pipeline.

### Phase 3 — Player & Streaming (partial)

- **3.1 Trickplay (Thumbnail Scrub)** — sprite-sheet generator +
  WebVTT thumbnail track served alongside the HLS playlist; player
  shows thumbnails on seek-bar hover.
- **3.2 Hardware Transcoding (NVENC/NVDEC)** — ADR-019. Capability
  detection at startup, configurable encoder selection, HW-accelerated
  HLS generation with graceful software fallback.
- **3.3 Skip Intro Detection** — Chromaprint-based fingerprinting,
  cross-episode matching, per-episode intro markers, "Skip Intro"
  button + manual override editor (`/admin/intros`). Later reworked to
  a pluggable frame-hash detector (ADR-020).
- **Skip Credits / next-episode** — ADR-021. Per-file credits detector
  from visual signals (edge + motion), feeding an end-of-episode
  marker.

### Phase 4 — Multi-User & Access Control

- **4.1 Authentication** — Identity bounded context (ADR-010, ADR-011)
  with FastAPI Users, cookie sessions, prefixed external IDs, bootstrap
  admin CLI.
- **4.2 User Profiles & Permissions** — Profile aggregate with kids
  flag, per-profile watch progress / collections / preferences,
  `allowed_library_ids` ACL filtering catalog reads, profile picker
  + management UI, profile avatar upload (Pillow centre-crop to WebP).
- **4.3 Runtime Settings (DB-backed)** — ADR-013 + ADR-014. Five
  operational tunable buckets (scheduler, thumbnail backfill, intro
  detection, streaming, avatar) moved out of `.env` into the
  `app_settings` table with per-bucket aggregates, snapshot+TTL
  facade (`RuntimeSettings`), one-time seed migrations, and a typed
  admin surface at `/api/v1/admin/settings`. Frontend forms ship at
  `/admin/system/settings` so edits propagate to consumers in
  seconds without restart (avatar storage subdir is the one caveat
  — lazy-cached at startup).
- 107 REST API endpoints across 9 bounded contexts, 2 530+ tests.

### Phase 6 — Scanner Deduplication (ADR-015)

- **6.1 Detection-only conflict queue** — ADR-015 Phase 1. New
  `MediaConflict` aggregate in `modules/media/` materialises
  content-identity collisions (Movie-vs-Movie TMDB id matches)
  detected by a post-enrich hook on `MediaEnrichedEvent`. Suggested
  action is pre-computed via a runtime-delta heuristic (`> 5 min` **and**
  `> 10%` flags a suspected different edit, never auto-merges).
  Read-only admin surface at `GET /api/v1/admin/conflicts` returns
  the pending queue with title/year projections of both sides.
  Polymorphic schema (`candidate_*_type` discriminator) ready for
  Series/Episodes in later phases without a migration.
- **6.2 Admin resolve UI + endpoint** — ADR-015 Phase 2.
  `POST /api/v1/admin/conflicts/{id}/resolve` (mark-distinct /
  merge-replace / merge-keep-both). MERGE soft-deletes the loser and
  fans out `MovieMergedEvent` to `watch_progress` + `collections`
  (repoint progress / list memberships, transfer file variants).
  `/admin/conflicts` page in homeflix-web with file-variant context
  per candidate.
- **6.3 Silent auto-merge** — ADR-015 Phase 3. Library-root health
  probe (`LibraryHealthPort`) distinguishes a real orphan
  (file missing, library mounted) from transient I/O; orphans are
  absorbed silently with a resolved-AUTO audit row + `is_auto`
  `MovieMergedEvent`. Audit view (pending / resolved-manual /
  resolved-auto tabs).
- **6.4 Tunables + bulk + fallback** — ADR-015 Phase 4.
  `scan_dedup` runtime-settings bucket (ADR-013) makes the
  runtime-delta thresholds tunable without a deploy;
  `POST /api/v1/admin/conflicts/bulk-mark-distinct` closes a whole
  selection in one transaction; `(normalized_original_title, year)`
  fallback matcher catches duplicates that never locked a TMDB id
  (queue-only, never auto-merged). Settings card + multi-select UI in
  homeflix-web.
- **6.5 Scheduled dedup sweep** — ADR-015 Phase 6.5. Periodic
  scheduler job walks `movies.list_all()` and re-runs the detector
  per movie — catches duplicates that landed after the original
  enrich and pairs that never matched TMDB (the detector accepts
  `tmdb_id=None` and runs the title+year fallback alone).
  `scan_dedup` bucket gains `sweep_enabled` (off by default) and
  `sweep_interval_minutes` (floor 15, default 1440); manual
  `POST /api/v1/admin/conflicts/sweep` endpoint runs the same pass
  on demand. Settings toggle + "Run sweep now" button in
  homeflix-web. ADR-015 closed.

### Phase 7 — Domain Hardening & Catalog Intelligence (ADR-016 → ADR-031)

Cross-cutting work since Phase 6.5, delivered as a run of small ADRs
rather than one large phase. Grouped by theme:

- **Domain modeling discipline** — MediaType promoted to a shared
  Value Object (ADR-016); domain invariants pushed into the domain
  layer (ADR-017); domain identifiers modeled as Value Objects at layer
  and BC boundaries (ADR-018); domain-exception usage semantics
  formalized (ADR-028); `TmdbId` promoted to the shared kernel and
  adopted in `catalog_requests` (ADR-031). This is the running
  execution of **2.2 Primitive Obsession**, one BC at a time.
- **Player & streaming** — hardware transcoding (ADR-019, item 3.2),
  pluggable intro detector by frame-hash (ADR-020), per-file credits
  detector (ADR-021), server-authoritative default track selection from
  per-user preference (ADR-026), and OCR of image-based subtitles
  (PGS/VOBSUB) into selectable text tracks (ADR-027).
- **Catalog & metadata** — multi-user subscriptions + fanout on catalog
  requests (ADR-022), localized metadata as a Value Object (ADR-023),
  provider-metadata reconciliation moved to the application layer
  (ADR-025), provider artwork mirrored to a storage port for durability
  (ADR-029), and multi-episode-per-file segments (ADR-030).
- **Cross-BC contracts** — published presentation contracts so modules
  can import each other's read shapes without reaching into internals
  (ADR-024).

- 145 REST API endpoints across 9 bounded contexts, ~3 340 tests (live
  count: `grep -rE '@router\.(get|post|put|patch|delete)' src/ | wc -l`).

---

## Open work

### Phase 2 — Hardening & Infrastructure (remaining)

#### 2.1 Docker & Compose

| | |
|---|---|
| **Teaches** | Multi-stage builds, containerization, infra as code |
| **Unlocks** | Reproducible dev env, CI pipeline, easy deployment, GPU passthrough for 3.2 |
| **Scope** | Dockerfile (backend), docker-compose with SQLite volume, optional PostgreSQL profile, optional GPU runtime profile |
| **Status** | WIP — draft in PR #104 (`feat/docker-setup`), pending review |

#### 2.2 Primitive Obsession Cleanup — *in progress*

| | |
|---|---|
| **Teaches** | Value Object design, domain modeling discipline |
| **Unlocks** | Stronger type safety, self-documenting domain |
| **Scope** | Audit codebase for raw `str`, `int`, `float` that carry domain meaning; extract to Value Objects in `shared_kernel` or module-level `value_objects`. Can be scope-bound to one BC at a time |
| **Progress** | Framework decided (ADR-018) and applied across `media`. In `catalog_requests`: `poster_url → ImageUrl` (#381) and `tmdb_id → TmdbId` shared-kernel VO (ADR-031, #382). Remaining BCs still hold some raw identifiers — pick up one BC at a time. |

#### 2.4 Subtitle Appearance (fix)

| | |
|---|---|
| **Teaches** | Browser text rendering pipeline, WebVTT spec, HLS.js internals |
| **Unlocks** | Readable subtitles with user-chosen colors/size |
| **Scope** | Investigate why `::cue` and custom overlay both failed; likely requires understanding HLS.js text track lifecycle in depth |

### Phase 5 — Observability & Resilience

#### 5.1 Webhooks & Notifications

| | |
|---|---|
| **Teaches** | Event-driven architecture, outbox pattern, external integrations |
| **Unlocks** | "Scan complete" notifications, integration with Telegram/Discord bots |
| **Scope** | Domain events → outbox table → webhook dispatcher; configurable endpoints per event type |

#### 5.2 Structured Logging & Metrics

| | |
|---|---|
| **Teaches** | Correlation IDs, structured JSON logs, Prometheus metrics |
| **Unlocks** | Debugging production issues, performance monitoring |
| **Scope** | Request-scoped correlation ID, structured log format, basic Prometheus endpoint (request count, latency, transcoding queue). Note: structlog with request_id middleware is already in place — this item is about exporting metrics, not the logging primitives. |

---

## Explicitly excluded

These features were evaluated and intentionally left out:

| Feature | Reason |
|---|---|
| Live TV & DVR | Completely different domain, enormous complexity, low personal utility |
| Music / Photos / Books | Scope creep — better served by Navidrome, Immich, Kavita respectively |
| Plugin system | Over-engineering for a personal project; high maintenance cost for low return |
| Native mobile/TV apps | Disproportionate investment — responsive web already covers the use case |
| DLNA | Legacy protocol with poor UX; Chromecast superseded it |
| SSO / LDAP | Enterprise-scale concern; overkill for a home server |
| Remote streaming (WAN) | Reverse proxy is an infra concern, not an app feature; can be added externally |

---

## How to read this document

- **Phases are sequential** but items within a phase can be parallelized.
- **"Depends on"** links indicate hard prerequisites.
- **"Teaches"** captures the architectural learning objective.
- **"Unlocks"** captures the user-facing or infra value.
- This document is updated as items are completed or re-prioritized.
