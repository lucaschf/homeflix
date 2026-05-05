# HomeFlix — Roadmap

> Last updated: 2026-05-05

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

## Shipped (Phases 1–4)

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
- **3.3 Skip Intro Detection** — Chromaprint-based fingerprinting,
  cross-episode matching, per-episode intro markers, "Skip Intro"
  button + manual override editor (`/admin/intros`).

### Phase 4 — Multi-User & Access Control

- **4.1 Authentication** — Identity bounded context (ADR-010, ADR-011)
  with FastAPI Users, cookie sessions, prefixed external IDs, bootstrap
  admin CLI.
- **4.2 User Profiles & Permissions** — Profile aggregate with kids
  flag, per-profile watch progress / collections / preferences,
  `allowed_library_ids` ACL filtering catalog reads, profile picker
  + management UI, profile avatar upload (Pillow centre-crop to WebP).
- 77 REST API endpoints across 7 bounded contexts, 2 200+ tests.

---

## Open work

### Phase 2 — Hardening & Infrastructure (remaining)

#### 2.1 Docker & Compose

| | |
|---|---|
| **Teaches** | Multi-stage builds, containerization, infra as code |
| **Unlocks** | Reproducible dev env, CI pipeline, easy deployment, GPU passthrough for 3.2 |
| **Scope** | Dockerfile (backend), docker-compose with SQLite volume, optional PostgreSQL profile, optional GPU runtime profile |

#### 2.2 Primitive Obsession Cleanup

| | |
|---|---|
| **Teaches** | Value Object design, domain modeling discipline |
| **Unlocks** | Stronger type safety, self-documenting domain |
| **Scope** | Audit codebase for raw `str`, `int`, `float` that carry domain meaning; extract to Value Objects in `shared_kernel` or module-level `value_objects`. Can be scope-bound to one BC at a time |

#### 2.4 Subtitle Appearance (fix)

| | |
|---|---|
| **Teaches** | Browser text rendering pipeline, WebVTT spec, HLS.js internals |
| **Unlocks** | Readable subtitles with user-chosen colors/size |
| **Scope** | Investigate why `::cue` and custom overlay both failed; likely requires understanding HLS.js text track lifecycle in depth |

### Phase 3 — Player & Streaming Evolution (remaining)

#### 3.2 Hardware Transcoding (VAAPI / NVENC)

| | |
|---|---|
| **Teaches** | FFmpeg hardware acceleration, capability detection, fallback chains |
| **Unlocks** | 4K HEVC playback without melting the CPU |
| **Scope** | Detect available HW encoders at startup, prefer HW pipeline in HLS generation, graceful fallback to software |
| **Depends on** | 2.1 (Docker — GPU passthrough config) |

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
