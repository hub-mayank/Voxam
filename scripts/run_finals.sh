#!/usr/bin/env bash
# Finals mode: the whole product behind ONE local address (http://localhost:5173), so a free tunnel can turn it into one https link.
# Browsers only allow the microphone on https or localhost: a tunnel gives other computers (the judges') the https they need.
#   FACULTY_TOKENS="mayank:$(openssl rand -hex 12)" scripts/run_finals.sh [--fresh]
#   TUNNEL=1 FACULTY_TOKENS=... scripts/run_finals.sh      # also starts a free Cloudflare quick tunnel if `cloudflared` is installed
# Everything else is the local profile (scripts/run_local.sh): same seeded vivas, same students, same voice models.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${FACULTY_TOKENS:?set a long faculty token first, for example: FACULTY_TOKENS=\"mayank:\$(openssl rand -hex 12)\" scripts/run_finals.sh}"
case "$FACULTY_TOKENS" in *demo-token*) echo "refusing the public demo token: choose your own secret" >&2; exit 1;; esac
PORT="${PORT:-8000}"
LOGS=".local"; mkdir -p "$LOGS"

pids=()
cleanup() { for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

if [ ! -d frontend/node_modules ]; then (cd frontend && npm install); fi
(cd frontend && npm run build)

# the backend, worker and seeded vivas; it keeps running in the background and prints the student codes into its log
PORT="$PORT" scripts/run_local.sh "$@" >"$LOGS/finals-backend.log" 2>&1 &
pids+=($!)
for _ in $(seq 1 120); do curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS "http://localhost:$PORT/health" >/dev/null || { echo "backend did not start: see $LOGS/finals-backend.log" >&2; exit 1; }

# the production build and /api -> the backend (vite.config.ts)
(cd frontend && npm run preview -- --host 127.0.0.1 --port 5173 --strictPort) >"$LOGS/finals-frontend.log" 2>&1 &
pids+=($!)
for _ in $(seq 1 30); do curl -fsS http://localhost:5173/api/health >/dev/null 2>&1 && break; sleep 1; done
curl -fsS http://localhost:5173/api/health >/dev/null || { echo "the app did not start: see $LOGS/finals-frontend.log" >&2; exit 1; }

if [ "${TUNNEL:-0}" = "1" ]; then
  if command -v cloudflared >/dev/null 2>&1; then
    cloudflared tunnel --url http://localhost:5173 >"$LOGS/finals-tunnel.log" 2>&1 &
    pids+=($!)
    for _ in $(seq 1 30); do grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOGS/finals-tunnel.log" 2>/dev/null | head -1 | grep -q . && break; sleep 1; done
    PUBLIC="$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOGS/finals-tunnel.log" | head -1 || true)"
  else
    echo "TUNNEL=1 but cloudflared is not installed: brew install cloudflared (free, no account needed for a quick tunnel)" >&2
  fi
fi

cat <<MSG

Voxam finals mode is running.
  This computer   http://localhost:5173/student?viva=local-dsa      faculty: http://localhost:5173/faculty
  Public link     ${PUBLIC:-(none yet: run  cloudflared tunnel --url http://localhost:5173   in another terminal)}
  Student codes   .local/codes.txt          Faculty token   the part of FACULTY_TOKENS after the colon
  Logs            $LOGS/finals-backend.log  $LOGS/finals-frontend.log  $LOGS/finals-tunnel.log
Anyone with the public link can open the pages: the faculty token and each student's one-time code are what protect the data.
Ctrl-C stops everything.
MSG
wait
