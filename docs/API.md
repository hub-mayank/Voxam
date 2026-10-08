# API guide for the frontend (Friend A)

Contract: `docs/openapi.json` (OpenAPI 3.1, generated, frozen at G0). Every operation has a description, every model an example. Generate a typed client from it, or browse `/docs` while the mock runs.

## Two ways to run it
**Mock backend** (static examples, no database, no secrets): every route returns its schema's example with header `X-Contract-Stub: 1`. Data does not change when you POST; path IDs are not looked up (any UUID works).
```
cd backend && source .venv/bin/activate
CONTRACT_STUB=1 FACULTY_TOKENS="demo:demo-token-0123456789" CORS_ORIGINS="http://localhost:5173" \
  python -m uvicorn app.api.main:app --port 8000
```
- Faculty: `Authorization: Bearer demo-token-0123456789`. Student: any token starting `st_` (join returns one).
- Make any stub fail: send `X-Mock-Error: <code>` (any code in the table below), e.g. `deadline_passed` on `/answer`.

**Real backend with seeded DEMO data** (SQLite file, real logic: sessions, timer, scoring view, overrides):
```
cd backend && source .venv/bin/activate
export FACULTY_TOKENS="demo:demo-token-0123456789" CORS_ORIGINS="http://localhost:5173" \
       ACCESS_CODE_PEPPER="dev-only-pepper-change-me" AUDIO_SIGNING_SECRET="dev-only-audio-secret"
python ../scripts/seed_demo.py                        # once: prints the DEMO students' access codes
python -m uvicorn app.api.main:app --port 8000
```
Everything seeded is fake and labelled DEMO (viva `demo-dsa`, students `DEMO001`..`DEMO006`, scores from a mock model). It shows every dashboard state: scored, low-confidence (needs review), overridden, in progress, joined-not-started. To start over delete `backend/viva_dev.db*` and reseed. The real backend refuses to start without `AUDIO_SIGNING_SECRET` (and `ACCESS_CODE_PEPPER` unless `REQUIRE_ACCESS_CODE=false`).

Environment: `FACULTY_TOKENS` (`name:token,...`), `CORS_ORIGINS`, `CONTRACT_STUB`, `DATABASE_URL` (default local SQLite), `ACCESS_CODE_PEPPER`, `AUDIO_SIGNING_SECRET`, `LLM_CHAIN` (default `mock`; the interviewer's providers), `REQUIRE_ACCESS_CODE` (default true; the code is required, D10), `CODE_MAX_ATTEMPTS` (5) and `CODE_LOCKOUT_SECONDS` (900), `ANSWER_LEASE_SECONDS` (60).
Not built yet: the voice WebSocket (task T4). Build the text flow; voice will reuse the same session, token, timer and `turn.idx`.

## Conventions
- JSON everywhere except uploads (`multipart/form-data`, field `file`), the audio and the CSV export.
- Timestamps: ISO-8601 UTC ending in `Z`. Durations: integer milliseconds, field names end in `_ms`.
- Auth: `Authorization: Bearer <token>`. Missing, unknown or rotated token: **401**. (Real backend: a student token only works on its own session; another session's token is 403.) Valid token, wrong role (student token on a faculty route or the reverse) or someone else's session: **403**. On 401 from a student route, rejoin.
- The reviewer name on an override comes from the faculty token. Never send it.
- Lists: `{"items": [...]}`. Sessions are paginated: `?limit=&cursor=`, response has `next_cursor` (null = last page).
- Statuses: `created, consented, in_progress, ended, scoring, scored, abandoned, failed`.
- `turns[].idx` counts spoken turns from 0; scoring evidence and the student's `turn.idx` use the same numbers.

## Errors
Every non-2xx response is `{"error": {"code", "message", "details"}}`. Branch on `code`:

| code | HTTP | when / what to do |
|---|---|---|
| `unauthorized` | 401 | no/unknown/replaced token (`details.reason`) |
| `forbidden` | 403 | wrong role or other student's session |
| `not_found` | 404 | no such viva/session/audio |
| `method_not_allowed` | 405 | |
| `validation_error` | 422 | `details.fields[{loc,message}]` |
| `invalid_upload` | 422 | bank/roster rejected, nothing stored; `details.rows[{row,field,message}]` |
| `invalid_credentials` | 403 | join: wrong ID or code (not distinguished) |
| `already_exists` | 409 | viva ID taken |
| `invalid_state` | 409 | action not allowed now (`details.status`, `required_status`) |
| `session_ended` | 409 | viva is over; code and token are dead |
| `deadline_passed` | 409 | answer too late and NOT recorded; show `details.closing_text`, then finish |
| `bad_client_seq` | 409 | `details.expected` |
| `rules_version_mismatch` | 409 | re-show rules (`details.current_rules_version`) |
| `range_not_satisfiable` | 416 | bad `Range` on audio |
| `audio_not_available` | 404 | the session has no recording (text mode) |
| `results_not_released` | 403 | student result requested before faculty released results |
| `rate_limited` | 429 | `details.retry_after_ms` (too many wrong access codes: the student is locked out for a while) |
| `provider_unavailable` | 503 | LLM down; retry the same request |
| `internal_error` | 500 | |

## Faculty flow
1. Paste token. Check it with `GET /faculty/vivas` (401 = bad token).
2. `POST /faculty/vivas` {title, subject, topics, difficulty} -> `Viva`.
3. `POST /faculty/vivas/{id}/questions` (file: `.json` array or `.csv` `id,topic,type,difficulty,text,key_points` with `|` between key points, plus an optional `source` column: `bank` or `ai-draft`). `config/question_bank.dsa.json` and `.csv` are a 30-question AI-drafted DSA bank (marked `ai-draft`: faculty must approve before real use). All-or-nothing: show `details.rows` on 422. Response has `warnings` (small bank). Locked once a student has joined.
4. `POST /faculty/vivas/{id}/roster` (file: `.csv` `student_id,name`). The response is the **only** time the plaintext `access_code`s are shown: show/print/download them now. Lost one: `POST .../roster/{student_id}/reset-code`.
5. `GET /faculty/vivas/{id}/sessions?status=&low_confidence=&search=&limit=&cursor=` for the list; `needs_review` marks low-confidence sessions that nobody has reviewed or overridden.
6. `GET /faculty/sessions/{sid}`: transcript, `scoring` (3 runs, median, per-dimension reason + `evidence` turn numbers), `feedback`, `overrides`, `integrity_events`, `audio`.
   - Play `audio.url` in an `<audio>` tag (signed, no header needed, ~15 min lifetime; refetch the session for a new one). It supports `Range`, so seeking works. Click-to-seek: set `currentTime = turn.t_start_ms / 1000`. `t_start_ms` is null in text mode.
   - Show `effective_total` (latest override else AI) and, if different, the AI total.
7. `POST /faculty/sessions/{sid}/override` {new_total 0-100, reason}. Only for `scored`/`failed`. To clear a low-confidence flag without changing the mark use `POST /faculty/sessions/{sid}/review` {note}. `POST /faculty/sessions/{sid}/rescore` queues scoring again (only from `failed` or `scored`).
   - To let students see their marks: `PATCH /faculty/vivas/{id}` {"results_visible_to_students": true} (default false).
8. Optional: `GET /faculty/vivas/{id}/export.csv` (download link; send the header via fetch + blob).

## Student flow
1. `POST /student/join` {viva_id, student_id, access_code} -> `session_token`, `rules_text`, `rules_version`, `status`. Keep the token in memory/sessionStorage. Joining again (page reload, second tab) while the session is not over returns a **new** token (`resumed: true`) and the old one gets 401; after the end you get `session_ended`.
2. Show `rules_text`. `POST /student/sessions/{sid}/consent` {accepted: true, rules_version}. Declining (`false`) changes nothing: the student cannot start.
3. `POST .../start` -> first AI turn, `deadline_at`, `remaining_ms`. Safe to call twice.
4. Loop: `POST .../answer` {text, client_seq (1, 2, 3...), t_start_ms?, t_end_ms?} -> next AI turn. On network timeout resend the **same** `client_seq` and text: you get the same reply, nothing is recorded twice. Stop when `turn.ended` is true or on `deadline_passed`.
5. Timer: poll `GET .../status` (every few seconds) and count down from `remaining_ms`, correcting with `server_now`. The server decides when time is up, not the browser.
6. After reload or rejoin: `GET .../status` gives `current_turn` and `last_client_seq` to continue (next answer is `last_client_seq + 1`).
7. After scoring: `GET /student/sessions/{sid}/result` gives total, dimension scores and feedback, but only if faculty released results (else 403 `results_not_released`; 409 `invalid_state` if not scored yet).

## Change policy after G0
`docs/openapi.json` is frozen: a test fails if the code and the file differ. **Additive changes** (a new optional field, a new endpoint, a new error code) are allowed without asking, but each needs one line in `docs/CHANGELOG-api.md` and a message to you before it lands. **Removals, renames and type changes need Mayank's approval.** Regenerate with `python scripts/export_openapi.py`.

## Not in the contract (yet)
Voice WebSocket (T4) · closing or scheduling a viva · AI-generated question banks · faculty accounts/login (tokens are issued by env) · deleting vivas, students or sessions.
