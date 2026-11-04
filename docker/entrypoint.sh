#!/usr/bin/env bash
#
# Container entrypoint: applies pending database migrations, then starts
# the API. Migrations are idempotent, so this is safe on every boot.
#
set -euo pipefail

echo "[entrypoint] Running database migrations..."
alembic upgrade head

echo "[entrypoint] Starting HomeFlix API on ${HOST}:${PORT}..."
exec uvicorn src.main:app --host "${HOST}" --port "${PORT}"
