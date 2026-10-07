# AI Viva

A fair, auditable 15-minute technical viva run by an AI interviewer (MSOT challenge, Problem 1).
The code owns the clock and follow-up policy; the LLM only classifies answers and phrases replies.
Scoring runs afterwards on the full transcript against a rubric, and every score cites transcript turns.

Status: text-mode interviewer, scorer, provider adapters (Gemini, Ollama, mock) with retry/fallback, telemetry and a call
cap are built. The HTTP API contract is frozen (`docs/openapi.json`) and implemented: a database-backed, restart-safe text
viva with faculty review. Not built yet: the scoring worker, voice and the dashboard.

## Quick start
Text mode runs fully offline with the mock LLM. It needs no Docker, database or API key.

    python3 -m venv backend/.venv && source backend/.venv/bin/activate
    pip install -r backend/requirements.txt
    python scripts/install_hooks.py                  # once per clone: secret scan before every commit
    python -m pytest -q                              # from the repo root

    cd backend
    python -m app.cli --llm mock                     # text viva, writes session.jsonl
    python -m app.score session.jsonl --llm mock     # score it, writes score.json

## API
    cd backend
    # mock backend for the frontend (static examples, no database):
    CONTRACT_STUB=1 FACULTY_TOKENS="demo:demo-token-0123456789" python -m uvicorn app.api.main:app --port 8000   # then open /docs

    # real backend with labelled DEMO data (SQLite file):
    export FACULTY_TOKENS="demo:demo-token-0123456789" ACCESS_CODE_PEPPER="dev-only-pepper-change-me" AUDIO_SIGNING_SECRET="dev-only-audio-secret"
    python ../scripts/seed_demo.py                  # prints the DEMO access codes
    python -m uvicorn app.api.main:app --port 8000

    # from the repo root, after a contract or model change:
    python scripts/export_openapi.py                 # docs/openapi.json (the frozen contract)
    python scripts/export_schema.py                  # db/schema.sql (PostgreSQL DDL, generated from the models)

Frontend guide: `docs/API.md`. Contract changes after G0 are listed in `docs/CHANGELOG-api.md`.

## Real models
Keys come from environment variables only, never from files in the repo (see `.env.example`).

    export GEMINI_API_KEY=...                        # never commit
    python -m app.list_models                        # pick GEMINI_MODEL from this list
    export GEMINI_MODEL=<name>
    python -m app.cli --llm gemini
    python -m app.cli --llm ollama                   # local, no key; needs OLLAMA_MODEL (and OLLAMA_HOST)
    python -m app.cli --llm gemini,ollama            # comma list = fallback order (or set LLM_CHAIN)

- Every live call counts against a daily cap, `LLM_DAILY_CALL_CAP` (default 30). Mock and Ollama are not counted.
- Tests that call a real provider are marked `live` and skipped unless you run `python -m pytest --live`.
- Provider calls are logged to `~/.cache/ai-viva/telemetry.jsonl` (override with `TELEMETRY_FILE`).

## Other commands
    python scripts/check_secrets.py                  # scan the repo for API-key shapes
    python scripts/make_personas.py                  # regenerate the scripted persona fixtures
    python scripts/bench_models.py <model> --runs 3 --delay 10   # live benchmark, counts against the cap
    python scripts/compare.py marks.csv              # AI vs human marks; columns session_id,ai_total,human_total

Results written under `results/` need a `.meta.json` sidecar (provider, model, date, git_sha, n); see `results/README.txt`.

## Layout
    backend/app/       interviewer, clock, policy, scorer, config; llm/ adapters; telemetry.py; session_state.py
                       api/ (FastAPI routes and schemas), services/ (student and faculty logic), db/ (models)
    backend/tests/     offline tests and persona fixtures
    config/            viva config (phases, rubric) and a sample question bank
    backend/app/db/    SQLAlchemy models; db/schema.sql is generated from them
    docker-compose.yml PostgreSQL for the later stages; not needed for local dev (SQLite)
    scripts/           benchmark, persona, secret-scan and comparison scripts
    docs/              SPEC, PLAN, DECISIONS, CREDITS, task reports in docs/reports/
    results/           raw evidence files
