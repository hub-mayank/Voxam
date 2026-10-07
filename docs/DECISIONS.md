# DECISIONS (append-only; newest at the bottom; each change needs a new entry)

Format: **ID title.** Decision. Why. Status (`accepted | proposed | pending`). Date.

**D1 Engine is framework-independent; code owns the clock and policy.** The LLM only classifies answers and phrases replies. Why: fairness and auditability (same structure for every student), testability. Accepted. 2026-10-05.

**D2 Interviewer and scorer are separate.** Scoring runs after the session on the full transcript, 3 runs → median, prompt + rubric version stored. Why: the PDF requires it and the live path must stay fast. Accepted. 2026-10-05.

**D3 All providers sit behind adapters with telemetry; mock by default.** Live calls are opt-in and capped. Why: evidence (latency, cost, error rates) comes from telemetry; free-tier and budget protection. Accepted. 2026-10-07.

**D4 Model: provisional `gemini-3.5-flash` for both roles.** Pending a paid-tier benchmark of the candidates. `gemini-2.5-*` unavailable to new users (404, 2026-10-06). Why: the only model with valid results so far. Pending. 2026-10-07.

**D5 Dev DB SQLite; target Postgres via Docker Compose; scoring queue is DB-backed (`FOR UPDATE SKIP LOCKED`), not Redis.** Why: fewer moving parts; Docker not yet installed (B3). Risk: SQLite hides concurrency bugs, so the load test must run on Postgres. Proposed; Claude Code to confirm or replace in T2a. 2026-10-07.

**D6 Scale proof in two layers.** Stub providers at 50/100/150 (tests our orchestration, DB, memory); live providers at ≤20 (tests vendors and rate limits). Every results row labelled `provider=stub|live`. Why: free tier and no credits make a live 150 impossible. Risk: judges may discount stub results, and the report must say so. Proposed. 2026-10-07.

**D7 Voice stack undecided.** T3 spike measures candidates; decision by G1 (Oct 10). Why: latency is the biggest technical risk; PDF suggests LiveKit Agents or Pipecat. Pending. 2026-10-07.

**D8 Cost target ≤ ₹20 per viva is ours, not MSOT's.** MSOT only says ₹500 per student is not viable. Verify with real pricing (T9). Accepted as an internal target. 2026-10-07.

**D9 Hinglish.** STT must transcribe Hinglish well (the WER test needs ≥20 clips across Indian-accented English and Hinglish). Hinglish interviewing stays a stretch goal. Accepted. 2026-10-07.

**D10 Student login = ID + one-time access code.** Why: ID alone allows impersonation, which breaks fairness. Accepted by Mayank, 2026-10-07. The code is required; `require_access_code` stays as a config flag (default true) for local dev and tests.

**D11 Two parallel Claude Code streams (CORE, VOICE).** Why: one worker cannot fit the plan in 10 days. Cost: double review load. Proposed. 2026-10-07.

**D12 D5 confirmed: SQLite dev, PostgreSQL target, DB-backed scoring queue, no Redis queue.** Why: the scoring job must be enqueued in the same transaction that ends the session (a Redis queue means two systems and a dual write); load is tiny for a database (150 concurrent sessions is roughly 5-8 writes/s, 350 scoring jobs in total); crash recovery is a `locked_at` column, not a visibility timeout. Conditions: (a) T2b claims jobs with a compare-and-set `UPDATE ... WHERE status='queued'` that runs on both databases, plus `FOR UPDATE SKIP LOCKED` on PostgreSQL, so the tested path is the production path; (b) SQLite is for dev and tests only: the stub load test (T7) must run on PostgreSQL, and until Docker is installed (B3) PostgreSQL is verified only by compiling the DDL, never by running it; (c) no Alembic or psycopg yet (not approved): schema comes from `create_all` or `db/schema.sql`, and any change after pilot data exists needs a manual migration, ask first; (d) the `redis` service in `docker-compose.yml` is unused and should go in T2b unless T4 needs pub/sub. Accepted. 2026-10-07.

**D13 The SQLAlchemy models are the schema; `db/schema.sql` is generated from them.** `scripts/export_schema.py` writes it and a test fails on drift. Changes from the hand-written DDL: `sessions.consent_at` is nullable (a session exists before consent); new `sessions.token_hash`, `deadline_at`, `created_at`; new `turns.client_seq` (idempotency, unique per session) and `turns.meta` (engine audit events such as `classify_error`); new `scores.low_confidence_reasons`; new `vivas.title/topics/difficulty/rules_version`; new tables `roster`, `access_codes`, `jobs`; CHECK constraints on enumerated columns; `turns.role` is `ai|student` only and `turns.idx` counts spoken turns, which is the number scoring evidence cites. Proposed. 2026-10-07.

**D14 API conventions frozen at G0.** All durations are integer milliseconds (`remaining_ms`, not `remaining_s`); timestamps are ISO-8601 UTC with `Z`; the audio URL in the session detail is signed and expires, so an `<audio>` tag works without an Authorization header; the question bank is locked once any student has joined; viva creation takes no phase timings or rubric weights (spec-bound, fixed by the platform); declining consent changes nothing; rejoin is allowed while a session is created, consented or in progress, and rotates the token. Proposed. 2026-10-07.
