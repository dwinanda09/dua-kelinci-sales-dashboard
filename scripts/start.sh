#!/usr/bin/env bash
# Start the stack in order: backend first, then the frontend once the backend
# reports healthy, then the Telegram bot if TELEGRAM_BOT_TOKEN is set in .env.
# Used by `make run` and ./setup.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose}"
WAIT_SECONDS="${WAIT_SECONDS:-120}"

step() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

wait_healthy() {  # wait_healthy SERVICE -> returns once its healthcheck passes
  local service="$1" cid status=""
  cid="$($COMPOSE ps -q "$service")"
  [ -n "$cid" ] || fail "Container $service tidak jalan."
  for _ in $(seq 1 "$WAIT_SECONDS"); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || true)"
    case "$status" in
      healthy) return 0 ;;
      unhealthy) break ;;
    esac
    sleep 1
  done
  $COMPOSE logs --tail 30 "$service" >&2 || true
  fail "$service belum sehat setelah ${WAIT_SECONDS} detik (status: ${status:-unknown}). Log di atas."
}

step "1/3 Backend: build dan start"
$COMPOSE up -d --build app

printf '\033[1m%s\033[0m' "2/3 Menunggu backend sehat"
wait_healthy app &
pid=$!
while kill -0 "$pid" 2>/dev/null; do printf '.'; sleep 2; done
wait "$pid"
echo " ok"

step "3/3 Frontend: build dan start"
$COMPOSE up -d --build --no-deps web
wait_healthy web

token="$(grep -E '^TELEGRAM_BOT_TOKEN=' .env 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
if [ -n "$token" ]; then
  step "Bot Telegram: build dan start"
  $COMPOSE --profile bot up -d --build --no-deps bot
fi

port="$(grep -E '^APP_PORT=' .env 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
step "Siap: http://localhost:${port:-8000}"
