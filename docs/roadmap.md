# HomeFlix — Roadmap

> Last updated: 2026-04-13

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

## Current state (Phase 1 — Foundation)

Completed:

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
- Responsive React frontend with MUI, TanStack Query, hls.js player
- i18n (pt-BR + en)
- 52 REST API endpoints, 1 450+ tests

---

## Phase 2 — Hardening & Infrastructure

Focus: solidify what exists, build shared infrastructure that later
features depend on.

### 2.1 Docker & Compose

| | |
|---|---|
| **Teaches** | Multi-stage builds, containerization, infra as code |
| **Unlocks** | Reproducible dev env, CI pipeline, easy deployment |
| **Scope** | Dockerfile (backend), docker-compose with SQLite volume, optional PostgreSQL profile |

### 2.2 Primitive Obsession Cleanup

| | |
|---|---|
| **Teaches** | Value Object design, domain modeling discipline |
| **Unlocks** | Stronger type safety, self-documenting domain |
| **Scope** | Audit codebase for raw `str`, `int`, `float` that carry domain meaning; extract to Value Objects in `shared_kernel` or module-level `value_objects` |

### 2.3 Scheduled Scan (Background Jobs)

| | |
|---|---|
| **Teaches** | Task scheduling, background workers, async job lifecycle |
| **Unlocks** | Foundation for trickplay generation, auto-enrichment, any future async pipeline |
| **Scope** | Cron-like scheduler (APScheduler or similar), library scan on configurable interval, job status endpoint |

### 2.4 Subtitle Appearance (fix)

| | |
|---|---|
| **Teaches** | Browser text rendering pipeline, WebVTT spec, HLS.js internals |
| **Unlocks** | Readable subtitles with user-chosen colors/size |
| **Scope** | Investigate why `::cue` and custom overlay both failed; likely requires understanding HLS.js text track lifecycle in depth |

---

## Phase 3 — Player & Streaming Evolution

Focus: bring the playback experience closer to commercial quality.

### 3.1 Trickplay (Thumbnail Scrub)

| | |
|---|---|
| **Teaches** | Heavy async processing pipeline, sprite sheet generation, FFmpeg image extraction, BIF/WebVTT-thumbnails spec |
| **Unlocks** | Visual seek — the single biggest UX gap in the player |
| **Scope** | Background job generates thumbnail grid per media file; player shows thumbnails on hover over seek bar |
| **Depends on** | 2.3 (background jobs) |

### 3.2 Hardware Transcoding (VAAPI / NVENC)

| | |
|---|---|
| **Teaches** | FFmpeg hardware acceleration, capability detection, fallback chains |
| **Unlocks** | 4K HEVC playback without melting the CPU |
| **Scope** | Detect available HW encoders at startup, prefer HW pipeline in HLS generation, graceful fallback to software |
| **Depends on** | 2.1 (Docker — GPU passthrough config) |

### 3.3 Skip Intro Detection

| | |
|---|---|
| **Teaches** | Audio fingerprinting (Chromaprint), cross-episode matching algorithms |
| **Unlocks** | "Skip Intro" button during playback |
| **Scope** | Analyze first 5 min of each episode in a season, find common audio segment, store start/end timestamps, player shows skip button |
| **Depends on** | 2.3 (background jobs) |

---

## Phase 4 — Multi-User & Access Control

Focus: make HomeFlix usable by more than one person on the network.

### 4.1 Authentication (JWT)

| | |
|---|---|
| **Teaches** | JWT lifecycle, refresh tokens, middleware auth, secure password storage |
| **Unlocks** | Per-user state isolation |
| **Scope** | Register/login endpoints, JWT access + refresh tokens, auth middleware, per-user preferences and progress |

### 4.2 User Profiles & Permissions

| | |
|---|---|
| **Teaches** | Row-level filtering, RBAC, multi-tenant patterns |
| **Unlocks** | Parental controls, library-level access |
| **Scope** | Admin vs. regular user roles, library visibility per user, content rating restrictions |

---

## Phase 5 — Observability & Resilience

Focus: production-grade operational visibility.

### 5.1 Webhooks & Notifications

| | |
|---|---|
| **Teaches** | Event-driven architecture, outbox pattern, external integrations |
| **Unlocks** | "Scan complete" notifications, integration with Telegram/Discord bots |
| **Scope** | Domain events → outbox table → webhook dispatcher; configurable endpoints per event type |

### 5.2 Structured Logging & Metrics

| | |
|---|---|
| **Teaches** | Correlation IDs, structured JSON logs, Prometheus metrics |
| **Unlocks** | Debugging production issues, performance monitoring |
| **Scope** | Request-scoped correlation ID, structured log format, basic Prometheus endpoint (request count, latency, transcoding queue) |

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
