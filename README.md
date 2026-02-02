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

This project follows **Clean Architecture** with **Domain-Driven Design** principles.

```
src/
├── domain/           # Business rules (entities, value objects)
├── application/      # Use cases and orchestration
├── infrastructure/   # External services (DB, APIs, filesystem)
├── presentation/     # REST API (FastAPI)
├── config/           # Settings and DI
└── i18n/             # Internationalization (en, pt-BR)
```

## Quick Start

### Prerequisites

- Python 3.12+
- [Poetry](https://python-poetry.org/docs/#installation)
- Node.js 20+ (for frontend, later)
- FFmpeg (for thumbnails, later)

### Installation

```bash
# Clone the repository
git clone https://github.com/lucaschf/homeflix.git
cd homeflix

# Install Poetry (if not installed)
curl -sSL https://install.python-poetry.org | python3 -

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
# Or: poetry run uvicorn src.main:app --reload
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

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Development

```bash
# Run development server
make dev

# Run tests
make test

# Run tests with coverage
make test-cov

# Run linter
make lint

# Format code
make format

# Type checking
make typecheck

# Run pre-commit on all files
make pre-commit

# Generate migration
make migration message="description"
```

## Contributing

1. Create a feature branch from `main`
2. Make your changes (pre-commit hooks will run automatically)
3. Write tests for new functionality
4. Ensure all tests pass: `make test`
5. Submit a pull request

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat: add new feature`
- `fix: resolve bug`
- `docs: update documentation`
- `refactor: improve code structure`
- `test: add tests`

## Documentation

- [Requirements](docs/homeflix-requirements.md) - Full feature specifications
- [ADRs](docs/adr/) - Architecture Decision Records
- [API Standards](docs/standards/) - Response format, exceptions, i18n

## Project Status

🚧 **Phase 1: Foundation** - In Progress

### Completed

- [x] Project structure with Clean Architecture layers
- [x] Domain layer
  - [x] Base models (DomainModel, ValueObject, DomainEntity, AggregateRoot)
  - [x] Exception hierarchy (DomainException, DomainValidationException, BusinessRuleViolationException)
  - [x] Media entities (Movie, Series, Season, Episode)
  - [x] Value objects (Title, Year, Duration, FilePath, Genre, Resolution)
  - [x] External IDs with prefixes (MovieId, SeriesId, SeasonId, EpisodeId)
  - [x] Repository interfaces (MovieRepository, SeriesRepository)
- [x] Application layer
  - [x] Exception hierarchy (ApplicationException, ResourceNotFoundException)
  - [x] Use cases (GetMovieById, GetSeriesById, ListMovies, ListSeries)
  - [x] DTOs for movies and series
- [x] Infrastructure layer
  - [x] Exception hierarchy (InfrastructureException, GatewayException, RepositoryException)
- [x] Configuration and settings
- [x] FastAPI main application
- [x] Pre-commit hooks (ruff, mypy)
- [x] CI pipeline

### Next Steps

- [ ] Repository implementations (SQLAlchemy)
- [ ] Database migrations
- [ ] REST API endpoints
- [ ] Media file scanning
- [ ] TMDB/OMDb integration

See [homeflix-requirements.md](docs/homeflix-requirements.md) for the complete roadmap.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

Built with ❤️ as a learning project for Clean Architecture and DDD.
