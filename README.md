# 🎬 HomeFlix

[![CI](https://github.com/lucaschf/homeflix/actions/workflows/ci.yml/badge.svg)](https://github.com/lucaschf/homeflix/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

Personal streaming platform for managing and playing movies/series from local storage.

## Overview

HomeFlix is a self-hosted media server that allows you to:

- 📁 Scan and organize your local video library
- 🎯 Auto-fetch metadata from TMDB/OMDb
- ▶️ Stream videos in your browser with multi-audio / multi-subtitle support
- 📊 Track watch progress per profile across devices
- 👪 Share the household with multiple profiles (kids flag, library ACLs, custom avatars)
- 📋 Create watchlists and custom collections per profile
- ⏭️ Skip intros automatically (Chromaprint fingerprinting) and scrub with thumbnail trickplay
- 🔍 Full-text search across the catalog

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| Frontend | React 18+, TypeScript, TanStack Query, MUI, hls.js |
| Database | SQLite (dev) / PostgreSQL (prod) |
| External APIs | TMDB, OMDb |

## Architecture

This project follows **Screaming Architecture** with **Clean Architecture** and **DDD** principles (see [ADR-008](docs/adr/ADR-008.md)).

```
src/
├── building_blocks/      # Domain-agnostic base (Entity, ValueObject, errors, event bus)
├── shared_kernel/        # Cross-module value objects (FilePath, LanguageCode, AudioTrack)
├── modules/
│   ├── media/             # Bounded Context: Media Catalog
│   ├── library/           # Bounded Context: Library Configuration
│   ├── watch_progress/    # Bounded Context: Watch Progress
│   ├── collections/       # Bounded Context: Watchlists & Custom Lists
│   ├── preferences/       # Bounded Context: Playback Preferences
│   ├── identity/          # Bounded Context: Users, Profiles, Sessions, ACL
│   └── catalog_requests/  # Bounded Context: Missing-title requests
├── infrastructure/       # Shared infra (database, scheduler, Base model)
├── config/               # Settings, DI containers
└── main.py
```

Each module follows the same internal layout — `domain/` (entities,
value objects, repository interfaces, domain services), `application/`
(use cases, DTOs, event handlers, ports), `infrastructure/`
(persistence, external integrations) and `presentation/` (FastAPI
routes + Pydantic schemas).

### Dependency Rule

Arrows indicate **allowed import directions** — a module may only import from what it points to:

```
modules → shared_kernel → building_blocks
Presentation → Application → Domain ← Infrastructure
```

- Modules do not import from each other (cross-module communication via domain events)
- Domain has no outward dependencies — Infrastructure depends on Domain (not the reverse), implementing its interfaces
- Application depends on interfaces defined in Domain
- Infrastructure implements those interfaces

**Example** — a media use case importing from each layer:

```python
from src.building_blocks.domain.entity import AggregateRoot          # building_blocks
from src.shared_kernel.value_objects.file_path import FilePath        # shared_kernel
from src.modules.media.domain.repositories import MovieRepository    # own domain
```

## Quick Start

### Prerequisites

- Python 3.12+
- [Poetry](https://python-poetry.org/docs/#installation)
- FFmpeg (for streaming/thumbnails)

### Installation

```bash
# Clone the repository
git clone https://github.com/lucaschf/homeflix.git
cd homeflix

# Full setup (dependencies + pre-commit hooks)
make setup

# Or manual installation
poetry install --with dev
poetry run pre-commit install
poetry run pre-commit install --hook-type commit-msg

# Run database migrations
make migrate

# Start the server
make dev
```

### Docker

For a one-command self-contained setup:

```bash
cp .env.example .env           # edit TMDB_API_KEY and media paths
docker compose up --build
```

The backend serves at http://localhost:8005. Migrations run
automatically on startup. Before shipping media, edit
`docker-compose.yml` to bind-mount your directories onto
`/media/movies` and `/media/series`:

```yaml
volumes:
  - /your/movies:/media/movies:ro
  - /your/series:/media/series:ro
```

Data, HLS cache, and thumbnails persist under `./data`, `./hls_cache`,
and `./thumbnails` on the host.

### Configuration

Copy the example environment file and configure:

```bash
cp .env.example .env
```

Key settings:

```env
# Database
DATABASE_URL=sqlite:///./homeflix.db

# Media directories (comma-separated)
MEDIA_DIRECTORIES=/path/to/movies,/path/to/series

# TMDB API (get yours at https://www.themoviedb.org/settings/api)
TMDB_API_KEY=your_api_key_here

# Optional: OMDb as fallback
OMDB_API_KEY=your_api_key_here
```

## API Documentation

Once running, access the interactive API docs:

- Swagger UI: http://localhost:8005/docs
- ReDoc: http://localhost:8005/redoc

## Development

```bash
make dev            # Run development server (port 8005)
make test           # Run all tests
make test-unit      # Run unit tests only
make test-cov       # Run tests with coverage
make lint           # Run linter
make format         # Format code
make typecheck      # Type checking (mypy)
make pre-commit     # Run pre-commit on all files
make migration message="description"  # Generate migration
make migrate        # Apply migrations
```

## Contributing

1. Create a feature branch from `develop`
2. Make your changes (pre-commit hooks will run automatically)
3. Write tests for new functionality
4. Ensure all tests pass: `make test`
5. Submit a pull request to `develop`

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat(media): add new feature`
- `fix(progress): resolve bug`
- `refactor(domain): improve code structure`
- `test(collections): add tests`

## Documentation

- [Requirements](docs/homeflix-requirements.md) - Full feature specifications
- [Roadmap](docs/roadmap.md) - Feature prioritization and next steps
- [ADRs](docs/adr/) - Architecture Decision Records
- [API Standards](docs/standards/) - Response format, exceptions, i18n

## Project Status

**Phases 1–4 shipped.** HomeFlix is a working multi-user household
streaming server with profile ACLs, automatic intro detection,
trickplay scrub thumbnails, and a scheduled scan/enrichment pipeline.

- 77 REST API endpoints across 7 bounded contexts
- 2 200+ tests
- Responsive React frontend with HLS player and per-profile UI

### Modules

| Module | Scope | Highlights |
|--------|-------|------------|
| **Media Catalog** | Movies, Series, Seasons, Episodes | File variants (ADR-006), HLS streaming, multi-audio/subtitle, FTS5 search, TMDB enrichment, filesystem scanner, intro markers, trickplay sprites |
| **Library** | Media source configuration | CRUD, metadata providers, scan settings, TrackSelector service (ADR-005) |
| **Watch Progress** | Playback tracking, scoped per profile | Save/resume, continue watching, auto-complete at 90% |
| **Collections** | Watchlist & Custom Lists, scoped per profile | Toggle watchlist, up to 10 custom lists with ordering |
| **Preferences** | Playback settings, scoped per profile | Audio/subtitle language, subtitle mode, quality, speed |
| **Identity** | Users, Profiles, Sessions, ACL | FastAPI Users + cookie auth (ADR-011), prefixed external IDs (ADR-002), Profile aggregate with `allowed_library_ids`, avatar upload (Pillow → WebP), bootstrap admin CLI |
| **Catalog Requests** | Missing-title tracking | Mark titles seen on TMDB but absent locally; auto-fulfilled when scanner picks them up |

### Frontend ([homeflix-web](https://github.com/lucaschf/homeflix-web))

- Login, profile picker, profile management (HBO/Netflix-inspired), avatar upload, account menu chip
- Hero carousel, genre browsing, full-text search with recent history
- HLS player: multi-audio, multi-subtitle with smart modes, quality selector, playback speed, keyboard shortcuts, auto-advance, skip-intro button, scrub thumbnails
- Continue watching, watchlist, custom lists, settings
- i18n (pt-BR + en), responsive mobile-first design

### What's Next

See [docs/roadmap.md](docs/roadmap.md) for the full roadmap. Open work:

- **Phase 2**: Docker & Compose, primitive obsession cleanup, subtitle appearance fix
- **Phase 3**: Hardware transcoding (VAAPI / NVENC) — depends on Docker
- **Phase 5**: Webhooks / outbox pattern, Prometheus metrics

## License

MIT License - see [LICENSE](LICENSE) for details.

---

Built with ❤️ as a learning project for Clean Architecture and DDD.
