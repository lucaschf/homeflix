#!/usr/bin/env bash
# Runs the Docker stack (docker-compose.yml) for `make up` and friends.
#   scripts/stack.sh up [--fresh] | down | logs | ps
#
# up      build what changed, start, wait until healthy, drop the images old builds left behind
#         --fresh: take the stack down first and rebuild without the build cache
# down    stop and remove the containers; ./data (database, artwork, caches) stays
# logs    follow the logs
# ps      what is running
#
# The web app joins when .env has COMPOSE_PROFILES=web (see docker-compose.yml).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
env_file="$root/.env"
compose=(docker compose -f "$root/docker-compose.yml" --project-directory "$root")

say() { printf '%s\n' "$*"; }
die() { printf 'stack: %s\n' "$*" >&2; exit 1; }

# A value from .env, or the default (no export: compose reads the file itself).
env_value() {
  local v
  v="$(sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$env_file" 2>/dev/null | tail -1 | tr -d '\r"'"'")"
  printf '%s' "${v:-$2}"
}

need_docker() {
  docker info >/dev/null 2>&1 || die "Docker is not running (start Docker Desktop, or the docker service)"
}

need_env() {
  [ -f "$env_file" ] || die ".env is missing: copy .env.example to .env and fill its Docker section"
  for key in SECRET_KEY MEDIA_ROOT; do
    [ -n "$(env_value "$key" "")" ] || die "$key is empty in .env (Docker section of .env.example)"
  done
}

up() {
  local fresh=""
  for arg in "$@"; do
    case "$arg" in
      --fresh) fresh=1 ;;
      *) die "up: unknown option $arg" ;;
    esac
  done
  need_env
  need_docker
  if [ -n "$fresh" ]; then
    say "stack: taking it down and rebuilding from scratch (./data stays)"
    "${compose[@]}" down --remove-orphans
    "${compose[@]}" build --no-cache --pull
  fi
  # Build first, on its own, so a failed build is not reported as a failed start. Only what changed
  # is rebuilt; containers whose image or config changed are recreated by up.
  if ! "${compose[@]}" build; then
    say "" >&2
    die "the build failed (above). Nothing was restarted: what was running still runs"
  fi
  if ! "${compose[@]}" up -d --remove-orphans --wait --wait-timeout 180; then
    say "" >&2
    say "stack: it did not come up healthy. State and the last lines of each log:" >&2
    "${compose[@]}" ps -a >&2 || true
    "${compose[@]}" logs --no-color --tail 30 >&2 || true
    say "" >&2
    say "stack: a taken port? set HOMEFLIX_PORT / HOMEFLIX_WEB_PORT in .env; \`make up FRESH=1\` rebuilds from scratch" >&2
    exit 1
  fi
  # Each rebuild leaves the previous backend image untagged; drop those (only HomeFlix's).
  docker image prune -f --filter "label=org.opencontainers.image.title=homeflix-backend" >/dev/null || true
  "${compose[@]}" ps
  local bind
  bind="$(env_value HOMEFLIX_BIND 127.0.0.1)"
  say ""
  say "stack: API at http://$bind:$(env_value HOMEFLIX_PORT 8005)"
  case ",$(env_value COMPOSE_PROFILES ""),"  in
    *,web,*) say "stack: web at http://$bind:$(env_value HOMEFLIX_WEB_PORT 3000)" ;;
  esac
}

case "${1:-}" in
  up) shift; up "$@" ;;
  down) need_docker; "${compose[@]}" down --remove-orphans ;;
  logs) need_docker; "${compose[@]}" logs -f --tail 100 ;;
  ps) need_docker; "${compose[@]}" ps -a ;;
  *) die "usage: scripts/stack.sh up [--fresh] | down | logs | ps" ;;
esac
