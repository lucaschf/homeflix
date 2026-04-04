.PHONY: help install dev test lint format migrate migration clean

# Default target
help:
	@echo "HomeFlix Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install all dependencies"
	@echo "  make install-dev   Install with dev dependencies"
	@echo "  make setup         Full setup (install + pre-commit)"
	@echo ""
	@echo "Development:"
	@echo "  make dev           Run development server"
	@echo "  make test          Run all tests"
	@echo "  make test-unit     Run unit tests only"
	@echo "  make test-cov      Run tests with coverage"
	@echo "  make lint          Run linter (ruff)"
	@echo "  make format        Format code (ruff)"
	@echo "  make typecheck     Run type checker (mypy)"
	@echo ""
	@echo "Pre-commit:"
	@echo "  make pre-commit    Run pre-commit on all files"
	@echo "  make pc-install    Install pre-commit hooks"
	@echo "  make pc-update     Update pre-commit hooks"
	@echo ""
	@echo "Database:"
	@echo "  make migrate       Apply all migrations"
	@echo "  make migration     Create new migration (use: make migration message='description')"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         Remove generated files"

# =============================================================================
# Setup
# =============================================================================

install:
	poetry install --without dev

install-dev:
	poetry install --with dev

setup: install-dev pc-install
	@echo "✅ Setup complete!"

# =============================================================================
# Development
# =============================================================================

dev:
	poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	poetry run pytest

test-unit:
	poetry run pytest -k "unit" -v

test-cov:
	poetry run pytest --cov=src --cov-report=html --cov-report=term-missing

lint:
	poetry run ruff check src tests

format:
	poetry run ruff check --fix src tests
	poetry run ruff format src tests

typecheck:
	poetry run mypy src

# =============================================================================
# Pre-commit
# =============================================================================

pre-commit:
	poetry run pre-commit run --all-files

pc-install:
	poetry run pre-commit install
	poetry run pre-commit install --hook-type commit-msg

pc-update:
	poetry run pre-commit autoupdate

# =============================================================================
# Database
# =============================================================================

migrate:
	poetry run alembic upgrade head

migration:
	poetry run alembic revision --autogenerate -m "$(message)"

# =============================================================================
# Cleanup
# =============================================================================

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
