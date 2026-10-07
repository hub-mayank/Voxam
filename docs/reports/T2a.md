# T2a API contract + data layer skeleton: 👍 done   (2026-10-07, CORE)
Part 0, 1, 2 and 3 all delivered. Every endpoint is a **stub** (example payload, `X-Contract-Stub: 1`); no real handler, no persistence wiring. Friend A can start now.

- Changed: Part 0 (5 commits): Planner update committed verbatim; `.claude/settings.json` rewritten; `.gitkeep`, stale `.gitignore` line and unused `import json` removed; README rewritten; D10 marked accepted (edited in place at Mayank's instruction, so DECISIONS is no longer strictly append-only for that line).
- Changed: contract (`backend/app/api/`): 19 operations (16 paths incl. `/health`), Pydantic v2 schemas with a description + example on all 39 models, uniform error body with 17 codes, faculty/student auth, `X-Mock-Error` header to trigger any error, signed-URL audio with Range. `scripts/export_openapi.py` -> `docs/openapi.json` (the freeze). `docs/API.md` for Friend A. `backend/app/session_state.py` (pure state machine).
- Changed: data layer (`backend/app/db/`): 10 tables, portable JSON/UUID/UTC types, CHECK + unique constraints, SQLite FK pragma. `db/schema.sql` is now **generated** from the models (`scripts/export_schema.py`).
- Changed: deps (pre-approved) in `backend/requirements.txt` + `docs/CREDITS.md`; DECISIONS D12 (D5 confirmed), D13 (schema source), D14 (API conventions).
- Evidence:
  - Start of task (after Part 0 cleanups): `python -m pytest -q` -> `109 passed, 2 skipped, 1 warning in 0.36s`.
  - End: `python -m pytest -q` -> `226 passed, 2 skipped, 2 warnings in 2.69s` (+15 state machine, +82 contract, +20 db); `python scripts/check_secrets.py` -> `secret scan clean`; `git status` clean; 85 tracked files.
  - Python 3.14 wheels, `pip install --dry-run --only-binary=:all:`: fastapi 0.142.2 (py3-none-any, MIT), uvicorn 0.54.0 (py3-none-any, BSD-3), pydantic 2.13.5 + pydantic_core 2.46.5 (**cp314** macOS arm64, MIT), SQLAlchemy 2.1.3 (**cp314**, MIT), python-multipart 0.0.32 (py3-none-any, Apache-2.0). All installed and working. Transitive: starlette 1.7.0, annotated-types, annotated-doc, click, opentelemetry-api (pulled by fastapi, Apache-2.0).
  - Freeze is real: changed one docstring -> `test_committed_openapi_json_matches_the_code` failed; reverted -> passed. Same for `db/schema.sql` (appended a line -> failed).
  - PostgreSQL proof is **compile-only**: `test_ddl_compiles_for_postgresql_without_a_server` compiles all 10 `CreateTable` and 5 `CreateIndex` with the postgresql dialect and checks `JSONB`, `UUID`, `TIMESTAMP WITH TIME ZONE`, `SERIAL`, `NUMERIC(5, 2)`, the partial unique index. No Docker or `psql` on this machine, so nothing ran on Postgres.
  - Mock server, `FACULTY_TOKENS=demo:demo-token-... python -m uvicorn app.api.main:app --port 8765` (also run as a test, `test_mock_server_boots_with_uvicorn`):
    ```
    GET /health                      -> 200 {"status":"ok"}
    GET /faculty/vivas  (Bearer)     -> 200, x-contract-stub: 1, first item id=dsa-midterm-2026
    GET /faculty/vivas  (no token)   -> 401 {"error":{"code":"unauthorized","message":"Missing, malformed, unknown or replaced token.","details":{"reason":"missing_token"}}}
    POST /student/join               -> 200 session_token=st_Zk3v..., status=created, resumed=False, rules_version=rules-v1
    POST .../answer + X-Mock-Error: deadline_passed -> 409 {"error":{"code":"deadline_passed",...,"details":{"closing_text":"Time is up. Thank you, that's the end of the viva.","deadline_at":"2026-10-12T05:45:12Z"}}}
    GET .../audio  Range: bytes=0-99 -> 206, accept-ranges: bytes, content-range: bytes 0-99/16044
    ```
  - Tests cover: auth matrix generated from the OpenAPI (13 faculty ops: no token 401, bad token 401, student token 403, faculty ok; 4 student ops: same mirrored; only `/health` and `/student/join` public); reviewer taken from the token (two tokens, two names; a `reviewer` body field is a 422); every model has a docstring and an example that validates and round-trips; every stub response validates against its own response model; all timestamps `Z`, naive rejected; no `*_s`/`*_seconds` fields; state-machine matrix (all 56 status x event pairs); examples are self-consistent (evidence points at student turns, weights sum to 100, run totals recompute, effective total = last override); CORS from env; audio Range 200/206/416 and signed URL; join code required vs `REQUIRE_ACCESS_CODE=false`; OpenAPI independent of env; contract fields all have a DB column; SQLite round-trip of UUID/JSON/UTC, FK enforcement, unique/CHECK/partial-unique constraints.
- Not verified / not run:
  - Anything on PostgreSQL (see above). Concurrency, load, restart: not run (no real handlers exist).
  - A typed client generated from `docs/openapi.json` (e.g. openapi-typescript) was **not** tried; "Friend A can build against it" is plausible, not demonstrated. First thing for Friend A to check: multipart upload fields and the 3.1 spec.
  - `Read(./.env)` deny semantics from a subdirectory cwd: not tested (I must not read `.env`).
  - Wall-clock time against the 0.75 d box: not measured; no part was cut.
- Risks found:
  - **`settings.json`**: all your patterns are syntactically valid; I changed nothing but added bare variants (`git push`, `git merge`, `git clean`, `git reset --hard`, `git commit -n`, `--no-verify`) because `X *` may not match the bare command. Limits of prefix rules: `git commit -m x --no-verify`, `git commit -am x -n`, `rm -fr` / `rm -r -f`, `git -C . push`, `git branch --delete --force` are **not** blocked. Also `python -m uvicorn`, `curl`, `pip` are not in the allow list so they prompt.
  - **Scorer output can't fill the contract yet**: `scorer.score_session()` returns only `run_totals`, not per-run dimension scores, so `RunScore.dimension_scores` needs a small scorer change in T5 (also `evidence_timestamps` is seconds, contract is ms). Median/representative-run aggregation is computed on read (D13) and not written anywhere yet.
  - Stub student auth accepts any `st_...` token and does not bind it to `{sid}`. Do not treat the mock as security. Real binding, hashing, rate limiting, the HMAC audio signature and its secret (`new env var`) are all T2b.
  - Models declare FKs but no `relationship()`, so the ORM does not order parent before child inserts (it bit my tests). T2b must flush parents first or add relationships.
  - Engine audit events (`classify_error`, `bank_exhausted`) have no row of their own; I put them in `turns.meta`. The fallback-model-per-turn visibility from T1 suggestion 1 is stored (`turns.model`) but **not exposed** in `Turn`.
  - Decisions I made that you may veto (D14): `remaining_ms` instead of your `remaining_s` (your own rule says durations are ms); bank locked once any student joins; declining consent is a no-op; timings/rubric not accepted at viva creation (spec-bound).
  - Additions you did not list: `GET /faculty/vivas/{id}/roster` (the dashboard needs to show who has not joined), `GET /health`, `X-Mock-Error`, signed `audio.url` (an `<audio>` tag cannot send a Bearer header).
  - Warnings: Starlette's `TestClient` says "install `httpx2`" (deprecation; not installed, not approved). Sample question bank is still too small (existing warning).
  - Access codes like `K7M2-9QXP` have ~40 bits; fine with rate limiting, weak against an offline attack if the DB leaks and the hash is plain SHA-256.
- Contract vs SPEC must-haves 1-8 + audit/replay (what is missing):
  1. Faculty setup: CSV/JSON bank ✓, subject/topics/difficulty ✓ (stored, but the engine does not use topics/difficulty yet). **Missing:** AI-generated bank from a syllabus with faculty approval (only `source`/`approved_by` fields reserved); editing a single question; closing/scheduling a viva.
  2. Login + rules + consent ✓. **Missing:** rules text is server-fixed, no faculty edit.
  3. Voice: **not in contract** (WebSocket described as TBD, T4). Latency fields none.
  4-5. Follow-ups, 15-min hard limit, visible timer ✓ (`deadline_at`, `remaining_ms`, `deadline_passed`). Timer is polling, no push.
  6. Marks + feedback ✓ for faculty. **Missing:** any student-facing result endpoint (SPEC says the student gets marks and feedback; policy unclear).
  7. Persistence: transcript, scores, reasoning ✓. Audio **upload** path is not part of the contract (arrives with voice); text mode has no audio, so `audio.available=false`.
  8. Dashboard: list, audio, transcript, scores, override ✓. **Missing:** re-score/retry a `failed` session (state machine allows `failed -> scoring`, no endpoint); a "mark reviewed" action (workaround: override with the same total); deleting/removing a student; faculty accounts (tokens from env).
  Audit/replay: evidence -> turn `idx` -> `t_start_ms` offset ✓; prompt + rubric version + model per score ✓. **Weak:** interviewer `prompt_version`/`model` per turn not exposed; asked question text needs a second call (`question_id` -> bank); integrity events are a stretch goal.
- Suggestions:
  1. **Challenge to the contract (do before G0 is final):** add `POST /faculty/sessions/{sid}/review {note}` and `POST /faculty/sessions/{sid}/rescore`. Today "mandatory faculty review" (SPEC) can only be cleared by a fake override with an unchanged mark, which pollutes the audit trail, and a `failed` scoring job has no recovery path. Both are cheap now and need approval later. (I did not add them: not in your list.)
  2. **Challenge to the freeze policy:** `docs/API.md` says every change needs approval, as assigned. With 9 days left and T2b/T4 certain to touch it (voice answers, LLM-down behavior), I suggest "additive changes allowed with a CHANGELOG line and a message to Friend A; only removals/renames/type changes need approval", else the freeze will be broken informally.
  3. T2b: expose `model`/`prompt_version` on `Turn` (additive, small) so a mid-session fallback is auditable from the dashboard (T1 suggestion).
  4. T5: refactor `score_session` to return per-run raw results before the scorer is wired in; contract and DB are shaped for it.
  5. Remove the unused `redis` service from `docker-compose.yml` in T2b (D12 d).
- Questions for Mayank: none blocking. Please accept or veto D13 and D14 (both `proposed`).
- Next task proposed: T2b (deps T2a; Friend A starts T6 against `docs/openapi.json` and `docs/API.md` now).
