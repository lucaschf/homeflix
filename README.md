# 🎬 HomeFlix

[![CI](https://github.com/lucaschf/homeflix/actions/workflows/ci.yml/badge.svg)](https://github.com/lucaschf/homeflix/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

Personal streaming platform for managing and playing movies/series from local storage.

## Overview

HomeFlix is a self-hosted media server that allows you to:

- 📁 Scan and organize your local video library
- 🎯 Auto-fetch metadata from TMDB/OMDb
- ▶️ Stream videos in your browser with subtitle support
- 📊 Track watch progress across devices
- 📋 Create watchlists and custom collections

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| Frontend | React 18+, TypeScript, TanStack Query, Video.js |
| Database | SQLite (dev) / PostgreSQL (prod) |
| External APIs | TMDB, OMDb |

## Architecture

This project follows **Screaming Architecture** with **Clean Architecture** and **DDD** principles (see [ADR-008](docs/adr/ADR-008.md)).

```
src/
├── building_blocks/      # Domain-agnostic base (Entity, ValueObject, errors, event bus)
├── shared_kernel/        # Cross-module value objects (FilePath, LanguageCode, AudioTrack)
├── modules/
│   ├── media/            # Bounded Context: Media Catalog
│   │   ├── domain/       #   entities, value_objects, repositories (ABCs), services
│   │   ├── application/  #   use_cases, dtos, event_handlers
│   │   ├── infrastructure/ # persistence, file_system, external APIs
│   │   └── presentation/ #   routes (movies, series, scan, enrichment, streaming)
│   ├── collections/      # Bounded Context: Watchlists & Custom Lists
│   │   ├── domain/
│   │   ├── application/
│   │   ├── infrastructure/
│   │   └── presentation/
│   ├── watch_progress/   # Bounded Context: Watch Progress
│   │   ├── domain/
│   │   ├── application/
│   │   ├── infrastructure/
│   │   └── presentation/
│   └── library/          # Bounded Context: Library Configuration
│       └── domain/
├── infrastructure/       # Shared infra (database, Base model)
├── config/               # Settings, DI containers
└── main.py
```

### Dependency Rule

```
modules → shared_kernel → building_blocks
Presentation → Application → Domain ← Infrastructure
```

- Modules do not import from each other (cross-module communication via domain events)
- Domain has no outward dependencies
- Application depends on interfaces defined in Domain
- Infrastructure implements those interfaces

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
- [ADRs](docs/adr/) - Architecture Decision Records
- [API Standards](docs/standards/) - Response format, exceptions, i18n

## Project Status

🚧 **Phase 1: Foundation** - In Progress

### Completed

- [x] Project structure with Screaming Architecture (ADR-008)
- [x] Building blocks (DomainModel, Entity, AggregateRoot, ValueObject, error hierarchy)
- [x] Domain events and in-process event bus
- [x] Dependency injection with `dependency-injector` (ADR-004)
- [x] Pre-commit hooks (ruff, mypy, conventional commits)
- [x] CI pipeline
- [x] Database migrations (Alembic)
- [x] **Media Catalog** module
  - [x] Entities: Movie, Series, Season, Episode with FileVariantMixin
  - [x] MediaFile variants with multiple resolutions (ADR-006)
  - [x] Filesystem scanning and media discovery
  - [x] TMDB/OMDb metadata enrichment (auto-enrich via domain events)
  - [x] REST API: CRUD, scan, enrichment, streaming, featured content
  - [x] HLS streaming with multi-audio/subtitle support
- [x] **Collections** module
  - [x] Watchlist (toggle, check, list)
  - [x] Custom lists (create, rename, delete, add/remove items)
- [x] **Watch Progress** module
  - [x] Save/get/clear progress
  - [x] Continue watching
- [x] **Library** module (domain layer only, ADR-005)
  - [x] Library entity, settings, TrackSelector service

### Next Steps

- [ ] Frontend (React + TypeScript)
- [ ] User authentication
- [ ] Full-text search

See [homeflix-requirements.md](docs/homeflix-requirements.md) for the complete roadmap.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

Built with ❤️ as a learning project for Clean Architecture and DDD.
