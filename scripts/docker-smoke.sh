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
chmod 0777 "$work/data" "$work/media"  # the container runs as uid 1000

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

"${compose[@]}" exec -T -w /tmp backend python -c "import src.config.containers" || fail "src not importable outside /app"
"${compose[@]}" exec -T backend test -f scripts/identity_create_admin.py || fail "admin bootstrap script missing"
check "identity bootstrap scripts can run"

"${compose[@]}" exec -T backend python scripts/rebase_media_paths.py --from /old --to /media >/dev/null \
  || fail "path rebase script does not run"
check "path rebase script can run"

[ "$(docker inspect -f '{{index .Config.Labels "pcs.id"}}' homeflix-backend)" = homeflix ] || fail "PCS labels missing"
check "PCS labels present"

# Start again with the optional paths set, to check they reach the container.
export HOMEFLIX_MEDIA_MODE=rw HOMEFLIX_ARTWORK=/media/artwork HOMEFLIX_HLS_CACHE=/media/hls_cache
"${compose[@]}" up -d --wait --wait-timeout 180 || fail "container did not restart with the optional paths"

"${compose[@]}" exec -T backend touch /media/x || fail "media is read-only with HOMEFLIX_MEDIA_MODE=rw"
check "media writable with HOMEFLIX_MEDIA_MODE=rw"

[ "$("${compose[@]}" exec -T backend printenv ARTWORK_STORAGE_DIRECTORY)" = /media/artwork ] || fail "HOMEFLIX_ARTWORK ignored"
[ "$("${compose[@]}" exec -T backend printenv HLS_CACHE_DIRECTORY)" = /media/hls_cache ] || fail "HOMEFLIX_HLS_CACHE ignored"
check "artwork and HLS cache paths configurable"

echo "docker setup: all checks passed"
