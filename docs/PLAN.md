# PLAN: AI Viva / Voxam (owner: Planner; last updated 2026-10-08)

Deadline **Sat 2026-10-17**. Target: submit **Fri 10-16 night**; Saturday is buffer (the cutoff time is unknown; see B5). Times IST.
Autonomy, reporting and rules: `CLAUDE.md`.
**Product name: Voxam** (chosen 2026-10-08). Use in README title, UI strings and demo; the repo and Python package names stay `ai-viva` until after submission. Trademark (IP India, classes 9/41/42) and domain checks: Mayank, no purchase (zero-spend).

## Planning principles
1. **De-risk voice first.** p95 < 2.5 s through STT → LLM → TTS is the schedule risk. Spike it before building around it.
2. **Evidence is a by-product.** Telemetry from the first provider call. The Test Report is generated from `results/`, never typed.
3. **Prove scale in layers.** Stub providers at 50/100/150 (tests *our* system); live providers at ≤20 (tests the vendors). Label every row. Judges may discount stub results; say so in the report.
4. **Honest partials beat claims.** Never cut: Test Report, 5 sample vivas, 5-run consistency, ≥20 WER clips, ≥10 human-marked vivas, privacy note, cost sheet.
5. **Interview quality is 25%**, the biggest single criterion. Evaluate the live interviewer on a real model, not only the plumbing.

## Capacity check (the plan was overbooked)
One worker needs ≈ 11.5 working days of tasks against 10 available. So there are **two Claude Code streams** in parallel, each in its own git worktree and branch:
- **CORE**: T0, T1, T2a, T2b, T5, T9, T10 (≈ 5.5 d)
- **VOICE**: T3, T4, T7 (≈ 5 d), starting once T1 is merged
Friend A: T6. Friend B and Mayank: evidence and blockers. Cost: you review two streams' reports, so reports must stay terse.

## Human blockers (only Mayank or the team can clear)
| ID | Blocker | Owner | By | Until cleared |
|---|---|---|---|---|
| B1 | Revoke the Gemini key pasted in chat; new key only in terminal env vars | Mayank | today | no live calls |
| B2 | **Zero-spend policy (Mayank, 10-08): no paid usage.** Free tiers + local models only. Mayank collects free keys (Gemini, Groq), checks Azure for Students, reports Mac specs | Mayank | 10-09 | live work limited to free quotas; stub proof for scale |
| B3 | Postgres via Homebrew now (`brew install postgresql@16`, D17); Docker Desktop only to verify the one-command compose run before submission | Mayank | 10-09 (Postgres), 10-13 (Docker) | Postgres claims unproven until installed |
| B4 | Friends: dev-sarthi = Friend A, Tejaa11 = Friend B, Friend C (third member, frontend + Python; GitHub username pending). Invite as collaborators (repo is private) | Mayank | 10-08 | friends cannot start |
| B5 | MSOT answered 10-08: **local-first architecture** (process on the client; if not feasible in the browser, a macOS app for iMacs; results + metadata synced to the central server), **Hindi and Hinglish required**, retention about 1 month (configurable by admin), pilot subjects **DSA and Web Development**. No credits or GPU offered. **Still unanswered:** submission cutoff time, finals date and format, team size, iMac specs, where the vivas run. Follow-up sent 10-08 | Mayank | follow-up answer pending | architecture decision (D22) and capacity plan depend on the iMac specs |
| B6 | ≥15 consenting volunteers (10 marked + 5 demo); consent form in `docs/consent/` | Friend B | 10-12 | no accuracy or demo evidence |
| B7 | Human marker (peer or faculty) for ≥10 vivas, using `docs/marking_sheet.csv` | Mayank | 10-14 | no accuracy evidence |
| B8 | Hosting for the finalists' live test | Mayank | 10-14 | submission still valid; finals not |

## Team (proposed; confirm with B4)
- **Claude Code**: engine, API, voice, scorer integration, load harness, scripts, doc drafts.
- **Friend A** (frontend + Python): faculty dashboard + student pages, against `docs/openapi.json` and the mock server (`docs/API.md`).
- **Friend B** (frontend + Python): consent, volunteers, human marks, audio clips + reference transcripts, demo vivas, screenshots; plus Python evidence scripts for T8 (`scripts/wer.py`, robustness table, marking-sheet -> compare adapter) in their own branches, reviewed by Claude Code.
- **Mayank**: decisions, blockers, merge approvals, demo video.

## Timeline
| Date | CORE | VOICE | Others | Gate |
|---|---|---|---|---|
| Wed 10-07 | T0, T1 | | Mayank: B1-B5 | |
| Thu 10-08 | T2a by noon, then T2b | T3 starts (after T1 merged) | Friend A starts T6; Friend B starts B6 | **G0** (contract) |
| Fri 10-09 | T2b | T3 | | |
| Sat 10-10 | T2b done | T3 decision | | **G1** voice stack |
| Sun 10-11 | T5 | T4 | | |
| Mon 10-12 | T5 done | T4 done | one human voice viva | **G2** |
| Tue 10-13 | T9 prep | T7 | Friend B runs vivas | |
| Wed 10-14 | T8 scripts | T7 runs | human marks done | **G3** feature freeze |
| Thu 10-15 | T8 runs, T9, T10 | T8 runs | 5 sample vivas | |
| Fri 10-16 | T10 done, report built | clean-clone test | demo video | **G4** code freeze 18:00; submit tonight |
| Sat 10-17 | buffer | | | |

## Gates
- **G0** contract frozen. API changes afterwards need supervisor approval and a note to Friend A.
- **G1** pick the voice stack from measured p50/p95 (≥30 turns, ≥2 stacks). Best p95 > 4 s → Plan B. **Status 10-08: provisional Stack A** (WebSocket + Silero + faster-whisper base + Piper); LLM leg was simulated, so T3b re-checks the Plan B trigger with a real LLM before G1 is final (Sat 10-10).
- **G2** one real human completes a voice viva; recording replays; timer and hard stop verified. Miss → Plan B.
- **G3** no new features. Fixes, evidence, docs only.
- **G4** code freeze; clean clone → one command → a full viva runs.

**Plan B (half-duplex):** student presses to speak and to submit; sentence-chunked TTS; document the latency honestly.

## Cut list (in this order if behind)
1. all stretch goals · 2. live-provider load above 20 (keep the stub proof) · 3. student-page polish · 4. dashboard extras beyond list / transcript+audio / scores / override · 5. self-hosted cost-variant detail.

## Tasks
Status: `todo | done`. A task is done when its report is on `main`. Mayank's pasted prompt names the task to run next; with no prompt, take the first `todo` in your stream whose deps are done.

### T0 Guardrails & hygiene: done, CORE, 0.5 d
- Clean-clone check: tests green. `.gitignore` additions: `.DS_Store`, `.llm_budget.json`, `CLAUDE.local.md`, `.claude/settings.local.json`.
- Quarantine invalid results: move `results/bench_20261006_012904.csv` (invalid run, fixture bug) to `results/_invalid/` with a README saying why. Nothing invalid stays in `results/`.
- `scripts/check_secrets.py` (regexes for API-key shapes; non-zero exit on a hit) + pre-commit hook installer.
- Call cap in the LLM adapter: `LLM_DAILY_CALL_CAP` (default 30), persisted counter, exceeding raises. `@pytest.mark.live` + `--live` flag (skipped by default).
- Seed `docs/CREDITS.md` (Gemini, httpx, pytest, ...).
- **Accept:** a test proves the cap raises after N calls; the secrets script flags a fake key in a temp file; live tests are skipped by default.

### T1 Telemetry & provider resilience: done, CORE, 0.5 d, deps T0
- Every provider call logs JSONL: ts, provider, model, kind (classify/phrase/score/stt/tts), latency_ms, tokens or audio-seconds, status, retries.
- Retry with backoff on 429/503/timeouts; ordered fallback chain; a fake provider that injects failures.
- Ollama adapter (no key) for free local dev.
- **Accept:** tests for 429 storm → retry → fallback; telemetry validates against a schema; Ollama adapter passes the same contract tests (skipped if not installed).

### Q0 Repo hygiene: done, CORE (rewrote CLAUDE.md; removed STATUS.md, invalid and stale bench results)

### T1c Free-first providers: todo, CORE, 0.5 d, deps T2b (scope in Mayank's pasted prompt)
- One OpenAI-compatible chat adapter (Groq, Cerebras, OpenRouter free models, any compatible endpoint) behind the existing adapter interface, with telemetry, cap and fallback chain support; no new dependency (httpx). Provider config from env only.
- **Accept:** same 18-check contract tests pass for it (HTTP faked); `--llm gemini,groq,ollama` works as a fallback chain.

### T1b Live baseline: todo, CORE, 0.25 d, deps free keys (env var only) + Mayank's go, T1c
- The repo holds zero live results after Q0, so scoring evidence must be re-earned. Run `scripts/bench_models.py` for the provisional model: 4 personas x 3 runs (about 12-15 live calls, inside the cap) from a clean tree, with a `provider=live` sidecar.
- **Accept:** results CSV + sidecar committed; strong > weak > idk; injection <= weak + 5. If any fails, report it honestly with the raw rows.

### T2a API contract: done, CORE, 0.75 d, deps T0, **G0** (freeze policy: additive changes with a CHANGELOG line + message to Friend A; removals/renames/type changes need approval)
- Priority order: (1) contract + stub mock server + `docs/openapi.json` + `docs/API.md` so Friend A is unblocked, (2) models, state machine, tests.
- Stub handlers return each schema's example payload (header `X-Contract-Stub: 1`), so `uvicorn` doubles as the mock backend for Friend A.
- Auth: faculty bearer tokens from env (`FACULTY_TOKENS=name:token,...`); reviewer identity comes from the token, never free text. Students: join returns a session token (stored hashed, rotates on rejoin). D10 (access code) is pending Mayank; implement behind `require_access_code` (default true).
- Student answer endpoint is idempotent on `client_seq`. Uniform error body `{error:{code,message,details}}` with an enumerated code list.
- SQLAlchemy models matching `db/schema.sql` (portable JSON types; SQLite dev, Postgres target). DB-backed job queue table for scoring (`FOR UPDATE SKIP LOCKED` on Postgres). Confirm or replace in DECISIONS D5.
- FastAPI route stubs + Pydantic schemas with example payloads → `docs/openapi.json`.
  Faculty: create viva, upload bank (CSV/JSON) and roster, list vivas/sessions, session detail, override (reviewer name + reason).
  Student: join (ID + one-time code), consent, start, answer (text mode), status/timer.
- **Accept:** `docs/openapi.json` is generated by a script and checked by a test; Friend A can build against it.

### T3 Voice spike (time-boxed 1.5 d): partial (report 10-08), VOICE, deps T1, **G1**
- Throwaway script: recorded WAV → STT → LLM → TTS; time-to-first-audio over ≥30 turns for ≥2 stacks. Candidates from SPEC (plus Gemini speech models, unverified). Take prices and limits from the vendors' current pages, not memory; record URL + retrieval date.
- WER on ≥5 Indian-accented clips (≥2 Hinglish) per candidate STT.
- Show how the existing `Interviewer` plugs in as the brain (code-owned clock and policy).
- No billing (B2)? Run local-only (faster-whisper + local TTS) and mark LLM latency `simulated`.
- Risk: the Mac venv is Python 3.14. Local speech packages (faster-whisper/ctranslate2, onnxruntime, torch) may lack 3.14 wheels. Check first; if so, report and ask before switching versions.
- **Accept:** `results/voice_spike/*.csv` + a DECISIONS entry choosing framework, STT, TTS, VAD with numbers. Paid calls are ask-first.

### T3b Close the voice spike's missing legs (0.5 d): todo, VOICE, same branch as T3, deps T3 + Mayank's installs/clips/go
- Real LLM leg: `bench_e2e.py` with Ollama (local floor) AND the provider actually intended for the live interviewer (Groq `gpt-oss-20b`, Gemini Flash-Lite) over ≥30 turns, with both sequential LLM calls measured. Calls counted via telemetry; cap raised for this task only (Groq ≤60, Gemini Flash-Lite ≤30).
- Real-voice WER on Mayank's 7 clips (whisper base/small; Groq whisper if key). whisper.cpp leg. Answers of 30-90 s (Whisper's 30 s window).
- TTS probes: Azure Speech en-IN voice (F0 key, if in `.env`), Piper `alba`. Licence decision applied (see PLAN notes below).
- **Accept:** `results/voice_spike/` updated, T3 report amended (not a new file), Plan B trigger evaluated with the real number, D19 text proposed for CORE to record.

### T2b Stateless engine & persistence: done, CORE, 1.5 d, deps T2a
- Rebuild `Interviewer` state from stored turns. Clock from the persisted server `started_at` (no process-local monotonic). Hard limit enforced server-side. Rejoin resumes at the right phase and time.
- Implement all T2a endpoints. One session per student per viva (rejoin allowed, retake not). Consent timestamp + rules version stored. Override logged.
- **Accept:** tests for rejoin mid-viva, double start, answer after deadline rejected, override wins and is logged, kill-and-restart worker continues a session.

### T4 Voice integration: todo, VOICE, 2 d, deps T3, T2b, **G2**
- Voice pipeline per the T3 decision → engine → TTS. WebSocket auth: session token in the first message. Add `websockets` dependency (CREDITS). Piper runs as a separate subprocess behind the TTS adapter (GPL isolation); voice `alba` (CC BY 4.0), not `lessac`. Server-driven visible timer; hard stop at 15:00 with graceful wrap-up; ~90 s answer cap; silence prompts; mic-muted and disconnect handling; rejoin.
- Audio saved incrementally; per-turn `t_start_ms/t_end_ms`; STT confidence stored; latency (student stops → first AI audio) logged per turn.
- **Accept:** a scripted bot completes a full 15-minute viva, stored and replayable; `results/latency_*.csv` with p50/p95; one human viva by Mayank.

### T5 Scorer integration: todo, CORE, 1 d, deps T2b
- Background worker: enqueue on session end; idempotent; retries. Stores scores, reasons, evidence, prompt + rubric versions, run totals and spread. Low-confidence flag adds STT-confidence and audio-quality signals. Evidence turn → audio offset for replay.
- `scripts/consistency.py`: 5 runs per transcript → variance CSV. Prompts moved to versioned files.
- **Accept:** worker survives a restart mid-job; `results/consistency_*.csv`; injection personas scored on a live model (ask-first).

### T6 Dashboard & student pages: todo, Friend A, 3 d, deps T2a (dashboard), T3 (student audio page)
- Dashboard: list vivas/sessions with filters; session detail with audio player, click-to-seek transcript, per-dimension score + reason + evidence links, low-confidence badge, override form (reviewer name + reason, history), bank and roster upload with validation errors, CSV export.
- Student pages: ID + code login, rules + consent, mic check, timer, end screen.
- **Accept:** every item shown in a screen recording; works against a mock backend.

### T7 Load harness: todo, VOICE, 1.5 d, deps T4
- Async bot clients streaming recorded PCM. Provider modes `stub` (latency profiles from T1/T3 measurements; **the stub STT must carry the measured capacity cap and service times from `results/voice_spike/stt_concurrency.csv`, a queueing model, or a 150-session stub run proves nothing about voice**) and `live`. Levels 10/25/50/100/150 (stub), 10-20 (live).
- Record p50/p95 latency, per-component error rate, dropped sessions, CPU/memory, DB connections. Find and report the breaking point. Include a 429-storm scenario.
- **Accept:** `results/load/*.csv`, each row labelled `provider=stub|live`; breaking point written down with what failed first.

### T8 Evidence runs: todo, CORE scripts + VOICE runs + Friend B, 2 d, deps T4, T5
- Follow-up quality: 3 personas through the real interviewer on a real model (ask-first) → transcripts.
- Scoring accuracy: `scripts/compare.py` on ≥10 human-marked vivas (`docs/marking_sheet.csv`).
- `scripts/wer.py` on ≥20 clips (Indian-accented English + Hinglish); reference transcripts by Friend B.
- Robustness table (drop, muted, silence, noise, rejoin). Fairness: ≥10 injection cases, off-topic, and an accent/language-mixing probe (same content, mixed language → non-Communication scores must not drop).
- **Accept:** raw results in `results/`; every Test Report row has a source file.

### T9 Cost & capacity: todo, CORE, 0.5 d, deps T7
- `docs/pricing.csv` (each price with URL, retrieval date, FX rate) + `scripts/cost_model.py`: ₹/viva and ₹/350 from telemetry; API vs self-hosted.
- Capacity plan: quota arithmetic for 150 concurrent (LLM requests/s, STT streams, TTS, DB connections, workers).
- **Accept:** every cost figure traces to telemetry × a priced row.

### T10 Docs & submission: todo, CORE drafts, Friend B + Mayank edit, 1.5 d, deps T8, T9
- README with a one-command run (tested on a clean machine); architecture diagram; design doc ≤3 pages; privacy note (storage, access, retention; retention pending MSOT, state the assumption); `scripts/build_report.py` generating the Test Report from `results/`; sample question bank + rubric config; `samples/` with 5 vivas + consent records; CREDITS.
- **Accept:** clean clone → one command → a viva runs; no number in the report without a source file.

### T11 Hosting for finals: todo, Mayank decides, deps B8
Compose production profile + deploy guide. Ask-first.

### Stretch (only after G3 and only if ahead)
Calibration mode in the dashboard · integrity signal: tab-switch (table exists) · Hinglish interviewing. Code round: skip.

## Supervision loop
1. Claude Code finishes a task and writes `docs/reports/T<id>.md`, then stops.
2. Planner reads the report and diff, re-runs tests where possible, and replies with a verdict and any plan changes.
3. Mayank says "next" or "merge". Plan changes are edits to this file by the Planner.
