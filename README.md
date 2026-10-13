# Voxam

Voxam is a fair, auditable 15-minute technical viva run by an AI interviewer (MSOT "AI Viva" challenge, Problem 1).
The code owns the clock and follow-up policy; the LLM only classifies answers and phrases replies.
Scoring runs afterwards on the full transcript against a rubric, and every score cites transcript turns.

Status: text-mode interviewer, scorer, provider adapters (Gemini, Ollama, mock) with retry/fallback, telemetry and a call
cap are built. The HTTP API contract is frozen (`docs/openapi.json`) and implemented: a database-backed, restart-safe text
viva with faculty review, and the scoring worker (queue, retries, restart-safe). Not built yet: voice and the dashboard.

## Quick start
Text mode runs fully offline with the mock LLM. It needs no Docker, database or API key.

    python3 -m venv backend/.venv && source backend/.venv/bin/activate
    pip install -r backend/requirements.txt
    python scripts/install_hooks.py                  # once per clone: secret scan before every commit
    python -m pytest -q                              # from the repo root

    cd backend
    python -m app.cli --llm mock                     # text viva, writes session.jsonl
    python -m app.score session.jsonl --llm mock     # score it, writes score.json

## Local profile (one command)
    scripts/run_local.sh            # API + scoring worker on SQLite, a seeded LOCAL viva, access codes printed; Ctrl-C stops it
    scripts/run_local.sh --fresh    # start over with an empty database
First run creates `backend/.venv` and installs the requirements. No cloud keys: with Ollama running and `llama3.2:3b` pulled the
interviewer and scorer use it, otherwise the offline mock model (plumbing only). Faculty token, port and models can be overridden
with `FACULTY_TOKENS`, `PORT`, `LLM_CHAIN`, `SCORER_LLM_CHAIN`. State lives in `.local/` (gitignored): database, logs, `codes.txt`.
The seeded viva is `local-dsa` (30 AI-drafted DSA questions, approved by the faculty token for local use only) with students
`LOCAL01`..`LOCAL10`. The voice WebSocket is specified in `docs/VOICE_PROTOCOL.md` (server: task T4).

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

## Real models (free tiers and local only)
Keys live in the environment or in a gitignored `.env` at the repo root (copy `.env.example`; variables already set in your shell win;
a git worktree uses the main checkout's `.env`). Nothing prints a key; `python -m app.envfile GROQ_API_KEY` shows only set/unset.

    python -m app.list_models                        # Gemini model IDs your key can call (one metadata request)
    python -m app.cli --llm gemini:gemini-3.5-flash-lite
    python -m app.cli --llm groq:openai/gpt-oss-20b  # any OpenAI-compatible endpoint: groq, cerebras, openrouter, or NAME_BASE_URL + NAME_API_KEY
    python -m app.cli --llm ollama:llama3.2:3b       # local, no key
    python -m app.cli --llm groq:openai/gpt-oss-20b,gemini:gemini-3.5-flash-lite,ollama:llama3.2:3b   # comma list = fallback order (or LLM_CHAIN)

- Zero-spend (D15): free tiers, free credits behind a hard spending limit, local models. Never a pay-as-you-go plan.
- Every provider attempt is counted per (provider, model) in a rolling 24 h window against the free-tier limits in `config/free_tier_limits.json`
  (re-verify them before an evidence run): refused at 90% of the daily limit (`FREE_TIER_MARGIN`) and spaced to stay under the per-minute limit.
  A refused provider is skipped and the next one in the chain serves. `LLM_DAILY_CALL_CAP` (default 30) is the global ceiling and the cap for
  models not in the file. Token limits (`tpm`, `tpd`) are enforced the same way. Mock and Ollama are never counted.
- Tests that call a real provider are marked `live` and skipped unless you run `python -m pytest --live`.
- Provider calls are logged to `~/.cache/ai-viva/telemetry.jsonl` (override with `TELEMETRY_FILE`).

## Scoring worker
    cd backend
    python -m app.worker                             # loop: end expired sessions, score due jobs; --once for one pass
    SCORER_LLM_CHAIN="groq:openai/gpt-oss-20b,ollama:llama3.2:3b" python -m app.worker     # default: LLM_CHAIN, then mock
    python ../scripts/consistency.py --llm mock --runs 5       # scorer variance per transcript (mock = plumbing only; --live needs approval)
Run as many workers as you like against one database: a job is claimed by one of them, and a worker that dies is replaced when its
5-minute lease runs out. A job that fails is retried after 30 s, then 60 s, then the session is marked `failed` (faculty can rescore);
a provider whose free-tier budget is used up delays the job instead of failing it.

## PostgreSQL
    brew install postgresql@16 && brew services start postgresql@16 && createdb ai_viva_test      # once
    echo 'TEST_DATABASE_URL=postgresql+psycopg://YOUR_USER@localhost/ai_viva_test' >> .env
    python -m pytest -q --postgres                   # the same suite, a fresh schema per test, dropped afterwards
    python scripts/prove_job_claim.py --jobs 600 --workers 8     # competing OS processes claim scoring jobs: none twice
The app uses `DATABASE_URL` (default: a local SQLite file); `postgresql://...` means the psycopg 3 driver.

## Other commands
    python scripts/check_secrets.py                  # scan the repo for API-key shapes
    python scripts/make_personas.py                  # regenerate the scripted persona fixtures
    python scripts/bench_models.py <model> --runs 3 --delay 10   # live benchmark, counts against the cap
    python scripts/compare.py marks.csv              # AI vs human marks; columns session_id,ai_total,human_total
    python scripts/free_tier_capacity.py --tokens-per-call 400 --tokens-per-score-call 3300   # what the free tiers allow (tokens are assumed)

Results written under `results/` need a `.meta.json` sidecar (provider, model, date, git_sha, n); see `results/README.txt`.

## Layout
    backend/app/       interviewer, clock, policy, scorer, config, worker; llm/ adapters; prompts/ (versioned scorer prompt); telemetry.py; session_state.py
                       api/ (FastAPI routes and schemas), services/ (student and faculty logic), db/ (models)
    backend/tests/     offline tests and persona fixtures
    config/            viva config (phases, rubric) and a sample question bank
    backend/app/db/    SQLAlchemy models; db/schema.sql is generated from them
    docker-compose.yml PostgreSQL for the later stages; not needed for local dev (SQLite)
    scripts/           benchmark, persona, secret-scan and comparison scripts
    docs/              SPEC, PLAN, DECISIONS, CREDITS, task reports in docs/reports/
    results/           raw evidence files
