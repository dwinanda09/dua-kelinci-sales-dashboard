#!/usr/bin/env bash
# Stop every process of this project, without deleting anything:
#   - all its containers (app, web, bot, test), kept so `make run` restarts them quickly
#   - backend, frontend and bot processes started by hand from this folder
#     (uvicorn, `npm run dev` / vite, bot.py), found by their working directory
# Data stays in the Docker volume.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd -P)"
COMPOSE="${COMPOSE:-docker compose}"

if docker info >/dev/null 2>&1; then
  $COMPOSE --profile bot --profile test stop
else
  echo "Docker tidak jalan; lewati container."
fi

cwd_of() {  # cwd_of PID -> working directory of the process
  readlink "/proc/$1/cwd" 2>/dev/null && return
  lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p'
}

killed=0
for pid in $(pgrep -f 'uvicorn api:app|vite|bot\.py' 2>/dev/null); do
  [ "$pid" = "$$" ] && continue
  case "$(cwd_of "$pid")" in
    "$ROOT"|"$ROOT"/*)
      echo "Stop proses lokal $pid: $(ps -o command= -p "$pid" | cut -c1-80)"
      kill "$pid" 2>/dev/null && killed=$((killed + 1)) ;;
  esac
done
[ "$killed" -gt 0 ] || echo "Tidak ada proses lokal dari folder ini."
