#!/usr/bin/env bash
#
# Container entrypoint — runs pending database migrations, then starts
# the FastAPI server. Migrations are safe to re-run on every boot.
#
set -euo pipefail

echo "[entrypoint] Running database migrations..."
alembic upgrade head

echo "[entrypoint] Starting HomeFlix API on ${HOST}:${PORT}..."
exec uvicorn src.main:app --host "${HOST}" --port "${PORT}"
