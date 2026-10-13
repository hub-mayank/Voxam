#!/usr/bin/env bash
# One command for the local profile: API + scoring worker on SQLite, a seeded LOCAL viva, access codes printed.
#   scripts/run_local.sh            start (creates backend/.venv on the first run)
#   scripts/run_local.sh --fresh    delete the local database first
# Overrides: PORT (8000), LLM_CHAIN, SCORER_LLM_CHAIN, FACULTY_TOKENS. No cloud keys needed: with Ollama running and llama3.2:3b pulled
# the interviewer and scorer use it, otherwise the offline mock model (plumbing only, not interview quality).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PORT="${PORT:-8000}"
LOCAL="$ROOT/.local"
mkdir -p "$LOCAL"

if [ "${1:-}" = "--fresh" ]; then
  rm -f "$LOCAL/viva.db" "$LOCAL/viva.db-wal" "$LOCAL/viva.db-shm" "$LOCAL/codes.txt"
  echo "local database removed"
fi

PY="$ROOT/backend/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "creating backend/.venv (first run) ..."
  python3 -m venv backend/.venv
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r backend/requirements.txt
fi

export FACULTY_TOKENS="${FACULTY_TOKENS:-demo:demo-token-0123456789}"
export ACCESS_CODE_PEPPER="${ACCESS_CODE_PEPPER:-dev-only-pepper-change-me}"
export AUDIO_SIGNING_SECRET="${AUDIO_SIGNING_SECRET:-dev-only-audio-secret}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///$LOCAL/viva.db}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:5173}"
if [ -z "${LLM_CHAIN:-}" ]; then
  if curl -fsS --max-time 2 http://localhost:11434/api/tags 2>/dev/null | grep -q 'llama3.2:3b'; then
    LLM_CHAIN="ollama:llama3.2:3b"
  else
    LLM_CHAIN="mock"
  fi
fi
export LLM_CHAIN
export SCORER_LLM_CHAIN="${SCORER_LLM_CHAIN:-$LLM_CHAIN}"

if curl -fsS --max-time 1 "http://localhost:$PORT/health" >/dev/null 2>&1; then
  echo "port $PORT is already serving something; stop it or set PORT=<other>" >&2
  exit 1
fi

"$PY" scripts/seed_local.py

cd backend
"$PY" -m uvicorn app.api.main:app --port "$PORT" >"$LOCAL/api.log" 2>&1 &
API_PID=$!
"$PY" -m app.worker --poll 3 >"$LOCAL/worker.log" 2>&1 &
WORKER_PID=$!
trap 'kill "$API_PID" "$WORKER_PID" 2>/dev/null || true' EXIT INT TERM

for _ in $(seq 1 60); do
  if curl -fsS --max-time 1 "http://localhost:$PORT/health" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$API_PID" 2>/dev/null; then echo "API failed to start; see $LOCAL/api.log" >&2; tail -20 "$LOCAL/api.log" >&2; exit 1; fi
  sleep 0.5
done

cat <<MSG

Voxam local profile is running.
  API + docs      http://localhost:$PORT/docs
  Faculty token   ${FACULTY_TOKENS#*:}   (header: Authorization: Bearer <token>)
  Viva id         local-dsa        students LOCAL01..LOCAL10, codes in .local/codes.txt
  Interviewer LLM $LLM_CHAIN        Scorer LLM $SCORER_LLM_CHAIN
  Logs            .local/api.log   .local/worker.log
Ctrl-C stops everything.
MSG
wait
