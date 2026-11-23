#!/usr/bin/env bash
# One-command setup for the sales dashboard and Telegram bot.
#
#   ./setup.sh              set up .env (asks for the bot token once) and start everything
#   ./setup.sh down         stop everything (data is kept in the Docker volume)
#   ./setup.sh logs         follow the logs
#
# Sales data (seeded from data/sales.csv on first setup only):
#   ./setup.sh data-status          what is in the database
#   ./setup.sh reseed [data/x.csv]  replace the sales data from a CSV in data/, then restart
#   ./setup.sh clean-data [--all]   delete the sales data (--all: recipients too); asks first
#   ./setup.sh reset                stop everything and delete the whole volume
#
# Non-interactive: TELEGRAM_BOT_TOKEN=123:abc ./setup.sh
set -euo pipefail

cd "$(dirname "$0")"
ENV_FILE=.env

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

# --- Docker --------------------------------------------------------------
command -v docker >/dev/null 2>&1 || fail "Docker belum terpasang. Install Docker Desktop: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || fail "Docker belum jalan. Buka Docker Desktop lalu jalankan ulang ./setup.sh"
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  fail "Docker Compose tidak ditemukan. Update Docker Desktop ke versi terbaru."
fi

# --- .env helpers ----------------------------------------------------------
get_env() {  # get_env KEY -> value in .env, or empty
  [ -f "$ENV_FILE" ] || return 0
  grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true
}

set_env() {  # set_env KEY VALUE -> replace or append KEY in .env
  local tmp
  tmp="$(mktemp)"
  if grep -qE "^$1=" "$ENV_FILE"; then
    awk -v k="$1" -v v="$2" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; next} {print}' "$ENV_FILE" > "$tmp"
  else
    cp "$ENV_FILE" "$tmp"
    printf '%s=%s\n' "$1" "$2" >> "$tmp"
  fi
  mv "$tmp" "$ENV_FILE"
}

# --- Subcommands -----------------------------------------------------------
seeder() {  # run the seeder in a one-off app container on the same volume
  $COMPOSE run --rm --no-deps app python -m sales.seed "$@"
}

restart_app_if_running() {
  if [ -n "$($COMPOSE ps -q app 2>/dev/null)" ]; then
    $COMPOSE restart app >/dev/null
    say "App di-restart; dashboard memakai data baru."
  fi
}

confirm() {  # confirm "question" -> continues only on "ya"
  if [ ! -t 0 ]; then fail "Butuh konfirmasi. Jalankan dari terminal, atau tambahkan --yes."; fi
  printf '%s Ketik ya untuk lanjut: ' "$1"
  read -r answer
  [ "$answer" = "ya" ] || fail "Dibatalkan."
}

case "${1:-up}" in
  down)  $COMPOSE --profile bot down; say "Berhenti. Data tetap tersimpan di volume."; exit 0 ;;
  logs)  exec $COMPOSE --profile bot logs -f ;;
  data-status)
    seeder status
    exit 0 ;;
  reseed)
    CSV_ARG=()
    if [ -n "${2:-}" ]; then
      case "$2" in
        data/*.csv) [ -f "$2" ] || fail "File tidak ditemukan: $2" ;;
        *) fail "Taruh CSV di folder data/ lalu jalankan: ./setup.sh reseed data/nama-file.csv" ;;
      esac
      CSV_ARG=(--csv "/app/$2")
    fi
    seeder reseed ${CSV_ARG[@]+"${CSV_ARG[@]}"}
    restart_app_if_running
    exit 0 ;;
  clean-data)
    ALL=""; YES=""
    for a in "${@:2}"; do
      case "$a" in --all) ALL="--all" ;; --yes) YES=1 ;; *) fail "Opsi tidak dikenal: $a" ;; esac
    done
    if [ -z "$YES" ]; then
      if [ -n "$ALL" ]; then confirm "Hapus data penjualan, daftar penerima, dan log kirim?"
      else confirm "Hapus data penjualan? Daftar penerima tetap ada."; fi
    fi
    seeder clear --yes $ALL
    restart_app_if_running  # the app seeds again from data/sales.csv on start
    exit 0 ;;
  reset)
    if [ "${2:-}" != "--yes" ]; then confirm "Hentikan semua container dan hapus seluruh volume (data penjualan dan penerima)?"; fi
    $COMPOSE --profile bot down -v; say "Berhenti dan volume dihapus. ./setup.sh akan seed ulang dari awal."; exit 0 ;;
  up)    ;;
  *)     fail "Perintah tidak dikenal: $1 (pakai: up, down, logs, data-status, reseed, clean-data, reset)" ;;
esac

# --- Configure ---------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
  cp .env.example "$ENV_FILE"
  say "Membuat $ENV_FILE dari .env.example"
fi
if [ ! -f config/recipients.csv ]; then
  cp config/recipients.example.csv config/recipients.csv
  say "Membuat config/recipients.csv (daftar sales manager; isi chat_id di sini atau di dashboard)"
fi

bot_username() {  # bot_username TOKEN -> @username from Telegram, or empty if rejected
  curl -fsS --max-time 10 "https://api.telegram.org/bot$1/getMe" 2>/dev/null \
    | sed -n 's/.*"username":"\([^"]*\)".*/\1/p' || true
}

# A token passed on the command line wins over the one in .env.
TOKEN="${TELEGRAM_BOT_TOKEN:-$(get_env TELEGRAM_BOT_TOKEN)}"
if [ -z "$TOKEN" ] && [ -t 0 ]; then
  echo
  say "Bot Telegram (opsional)"
  echo "Buat bot lewat @BotFather di Telegram (/newbot), lalu tempel tokennya di sini."
  echo "Tekan Enter untuk lewati dan jalankan dashboard saja."
  printf 'Token: '
  read -r -s TOKEN || true
  echo
fi

BOT_NAME=""
if [ -n "$TOKEN" ]; then
  BOT_NAME="$(bot_username "$TOKEN")"
  # Check before saving, so a mistyped token never ends up in .env.
  [ -n "$BOT_NAME" ] || fail "Token bot ditolak Telegram (atau tidak ada internet). Cek tokennya lalu jalankan ulang ./setup.sh"
  set_env TELEGRAM_BOT_TOKEN "$TOKEN"
  say "Token valid: @$BOT_NAME"
fi

APP_PORT="$(get_env APP_PORT)"
APP_PORT="${APP_PORT:-8000}"
[ -z "$(get_env DASHBOARD_URL)" ] && set_env DASHBOARD_URL "http://localhost:$APP_PORT"

# --- Start -----------------------------------------------------------------
echo
say "Membangun dan menjalankan container (pertama kali bisa 2-3 menit)..."
# Backend first, frontend once the backend is healthy, then the bot if a token is set.
COMPOSE="$COMPOSE" ./scripts/start.sh

printf 'Menunggu dashboard siap'
for _ in $(seq 1 60); do
  if curl -fsS --max-time 2 "http://localhost:$APP_PORT/api/health" >/dev/null 2>&1; then
    echo
    echo
    say "Siap."
    echo "  Dashboard : http://localhost:$APP_PORT"
    if [ -n "$TOKEN" ]; then
      echo "  Bot       : https://t.me/$BOT_NAME  (kirim /help)"
      [ -z "$(get_env TELEGRAM_ALLOWED_CHAT_IDS)" ] && \
        warn "  Catatan   : bot terbuka untuk siapa saja. Batasi lewat TELEGRAM_ALLOWED_CHAT_IDS di $ENV_FILE."
    else
      echo "  Bot       : tidak aktif (isi TELEGRAM_BOT_TOKEN di $ENV_FILE lalu jalankan ./setup.sh lagi)"
    fi
    echo "  Penerima  : config/recipients.csv atau tab 'Kirim Telegram' di dashboard"
    echo "  Berhenti  : ./setup.sh down"
    exit 0
  fi
  printf '.'
  sleep 2
done
echo
fail "Dashboard belum merespons setelah 2 menit. Cek log: ./setup.sh logs"
