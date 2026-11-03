#!/usr/bin/env bash
#
# Smoke test for the Docker setup: builds the image through docker-compose.yml,
# starts it against throwaway data and media folders, and checks that
# migrations ran, the API answers, the healthcheck passes and the process is
# not root. Leaves nothing behind.
#
#   scripts/docker-smoke.sh
#
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
project="homeflix-smoke"
port="${SMOKE_PORT:-18005}"
base="http://127.0.0.1:${port}"

mkdir -p "$work/data" "$work/media/movies"
chmod 0777 "$work/data"  # the container runs as uid 1000

export HOMEFLIX_APP_ENV=development HOMEFLIX_COOKIE_SECURE=false
export SECRET_KEY="smoke-$(date +%s)"
export MEDIA_ROOT="$work/media" HOMEFLIX_MEDIA_DIRECTORIES=/media/movies
export HOMEFLIX_DATA="$work/data" HOMEFLIX_PORT="$port"
compose=(docker compose -f "$root/docker-compose.yml" -p "$project")

cleanup() {
  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$work" 2>/dev/null || true
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  "${compose[@]}" logs --no-color --tail 80 >&2 || true
  exit 1
}
check() { echo "ok   $*"; }

"${compose[@]}" up -d --build --wait --wait-timeout 180 || fail "container did not become healthy"
check "image built, container healthy"

curl -fsS "$base/health" | grep -q '"status":"healthy"' || fail "/health"
check "/health answers"

[ -s "$work/data/homeflix.db" ] || fail "no database in the data volume"
# Read the logs first: under pipefail, `logs | grep -q` fails when grep exits early (SIGPIPE).
logs="$("${compose[@]}" logs --no-color backend)"
grep -q "Running upgrade" <<<"$logs" || fail "migrations did not run"
check "migrations ran into the data volume"

[ "$("${compose[@]}" exec -T backend id -u)" = 1000 ] || fail "not running as uid 1000"
check "runs as uid 1000"

"${compose[@]}" exec -T backend ffmpeg -version >/dev/null || fail "ffmpeg missing"
check "ffmpeg available"

"${compose[@]}" exec -T backend sh -c 'touch /media/x 2>/dev/null' && fail "media is writable"
check "media mounted read-only"

[ "$(docker inspect -f '{{index .Config.Labels "pcs.id"}}' homeflix-backend)" = homeflix ] || fail "PCS labels missing"
check "PCS labels present"

echo "docker setup: all checks passed"
