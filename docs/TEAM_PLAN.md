# Voxam prototype: team plan v2 (2026-10-13 evening, IST)

**Goal (prototype):** by **Thu 10-15 12:00** a student takes a ~15-minute *voice* viva in the browser on the **local profile** (no cloud keys), it is stored and scored (3 runs), and faculty see transcript, audio, scores, reasons and evidence in the dashboard.
**Status today:** backend done and merged: engine, scoring worker, voice WebSocket (stub and real whisper.cpp + Piper), one-command local run. **No frontend exists yet.** Nothing from teammates is pushed.
**After the prototype:** model router, cost-per-viva meter, sync bundle, live baseline, load test, evidence runs, report.

## 1. What changed in v2 (read this first)
Parth and Bhavesh work with **free-tier AI tools** (plus Antigravity); Tejas has Pro tools. Free tools drift on long, open-ended tasks, so v2 changes the work, not the people's effort:
- **Claude builds the risky foundations**: the frontend scaffold with a *typed* API client and ready-made hooks (CL-4), and the browser voice SDK (CL-5). Teammates build **screens on top of typed hooks**, which makes invented fields and endpoints fail the compiler instead of reaching review.
- **Cards are smaller** (≤ 300 changed lines, a few named files, one "Done when"), ordered by priority (P1 must, P2 should, P3 if time).
- **Every PR passes mechanical gates** before a human looks: `npm run check` and `python scripts/check_paths.py <name>` (section 5).
- Tejas keeps evidence and data and takes the report generator and privacy note, which suit Pro tools.

## 2. Context pack (read in this order, ~15 min)
1. `README.md`: what exists and the run commands (`scripts/run_local.sh` starts everything).
2. `docs/API.md` + `docs/openapi.json`: the HTTP contract. Mock backend: `CONTRACT_STUB=1` (see API.md).
3. `docs/VOICE_PROTOCOL.md`: the WebSocket contract (Bhavesh uses it only through the SDK).
4. `docs/GLOSSARY.md`: every term and ID in one line each.
5. `docs/DECISIONS.md`: D1 (code owns the clock), D10 (ID + access code), D14 (API conventions), D19 (voice stack).

**How it works in six lines:** student joins with ID + one-time code, accepts rules, starts. Each answer goes to the engine, which classifies it and picks the next question by code (clock and policy are ours); the LLM only phrases. Turns are stored with audio offsets. When the session ends, a worker scores it 3 times and stores the median with reasons and evidence turns. Faculty review, override, export. Voice = browser mic → WebSocket → STT → engine → TTS → browser.

## 3. Who owns what (enforced by `docs/ownership.json`)
| Person | Tools | Owns | Paths (only these) |
|---|---|---|---|
| **Parth** (dev-sarthi) | free AI + Antigravity | Faculty dashboard screens | `frontend/src/faculty/**` |
| **Bhavesh** (Src-Bhavesh) | free AI + Antigravity | Student screens, QA, demo script | `frontend/src/student/**` except `voice/` and `session/`; `docs/qa/**`, `docs/DEMO_SCRIPT.md` |
| **Tejas** (tejaa11) | Pro tools | Evidence and data, report generator, privacy note | `docs/consent/**`, `config/question_bank.webdev.*`, `evidence/**`, `scripts/wer.py`, `scripts/build_report.py`, `docs/PRIVACY.md`, `docs/marking_sheet.csv` |
| **Mayank** | | Reviews and merges, keys, decisions, MSOT | n/a |
| **Claude** | | Frontend foundation, voice SDK, backend, voice server, first-pass review | everything else, incl. `frontend/src/{api,shared,student/voice,student/session}/**` |

## 4. Schedule and milestones
| When | Claude | Parth | Bhavesh | Tejas |
|---|---|---|---|---|
| **Tue 10-13 night** | CL-4 foundation | PA-0 | BH-0 | TJ-1, TJ-2, TJ-3 |
| **Wed 10-14** | CL-4 merged by 10:00, then CL-5 SDK by 18:00, reviews | PA-1, PA-2, PA-3 | BH-1, then BH-2 when CL-5 lands | TJ-2 done, TJ-3 done; evening TJ-4 |
| **Thu 10-15** | streaming reply, hands-free, reviews | PA-4, PA-5 | BH-2, BH-3, BH-4 | TJ-5 volunteers' vivas, TJ-7 |
| **Fri 10-16** | evidence, docs, **code freeze 18:00** | PA-6, PA-7, bugs | BH-5, bugs | TJ-6, TJ-8 |

- **M1 Wed 12:00:** foundation merged; student text flow and faculty list/detail run against the real backend (`scripts/run_local.sh`).
- **M2 Wed 22:00:** push-to-talk voice in the browser on Mayank's Mac.
- **M3 Thu 12:00:** hands-free, hard stop, audio replay in the dashboard, Mayank's own viva. **Feature freeze Thu 18:00.**
- **Slip rule:** if M2 slips past Thu 06:00 we ship push-to-talk only. P3 cards are the first thing cut.

## 5. Rules and rails for everyone
**Rules**
- Branch `feat/<name>-<card>` from `main`, one card per PR, ≤ 300 changed lines. **Only Mayank merges.** Never push to `main`.
- Edit only your own paths. Need another file? Say so in the PR; do not edit it.
- No keys, no real data, no audio in git. `python scripts/check_secrets.py` before every PR.
- AI tools are fine: one line per tool in `docs/CREDITS.md`. No `Co-Authored-By` or "generated with" lines in commits.
- Frontend style: function components, single quotes, no semicolons, 2-space indent, one component per file, plain CSS (no UI library, no Tailwind).
- Blocked more than 30 minutes? Post it in the group chat with the PR link or exact error.

**Rails against AI mistakes (use all of them)**
1. **Contract first.** Use only the types in `frontend/src/api/schema.ts` and the hooks from `src/api` and `src/student/{session,voice}`. If a field or endpoint is not there, it does not exist: stop and ask. `tsc` failing means the AI invented something.
2. **One card per AI session.** Paste the card text and the named files, nothing else. Do not ask for "the whole dashboard".
3. **Diffs, not rewrites.** If the tool wants to change files that are not in the card, refuse and re-prompt. `check_paths.py` will catch it anyway.
4. **No new dependencies.** Allowed: `react`, `react-dom`, `react-router-dom`, `typescript`, `vite`, `vitest`, `eslint`. Anything else needs Mayank's yes.
5. **Run before you push:** `cd frontend && npm run check` (types + lint + tests) and `python scripts/check_paths.py <name>`. Paste both outputs in the PR.
6. **Prove it:** a screenshot from the real seeded backend (`scripts/run_local.sh`), not only the mock.
7. **Ask the AI to list its assumptions** ("which file and line did you rely on?") and put the answer in the PR.
8. **Failing review is normal.** Claude's first-pass comment lists exact fixes; give them to the AI as the next prompt.

## 6. Task cards
Priority: **P1** must for the prototype, **P2** should, **P3** if time. Each card: **Files**, **Do**, **Done when**. Hooks and types come from CL-4/CL-5; their names are fixed here so you can start from the contract.

### Claude
- **CL-4 Frontend foundation (P1, Wed 10:00).** `frontend/`: Vite + React + TypeScript; typed client generated from `docs/openapi.json` (`src/api/schema.ts`, `npm run gen:api`); `src/api/client.ts` (auth header, typed `ApiError` with `code`, safe retry); hooks `useFacultyApi()` and `useStudentSession()` (join, consent, start, answer with idempotent `client_seq`, status/timer re-sync, error codes); router with a placeholder file per screen under `src/faculty/` and `src/student/screens/`; shared `Page`, `Table`, `Badge`, `Button`, `Modal`, `ErrorBanner`; fixtures from the mock backend; `npm run check`. **Done when:** `npm run dev` shows the login page and `npm run check` passes.
- **CL-5 Browser voice SDK (P1, Wed 18:00).** `src/student/voice/`: AudioWorklet capture to 16 kHz PCM16, WebSocket client for `docs/VOICE_PROTOCOL.md`, playback queue with interrupt, `useVoiceSession()` (state, transcript, aiText, remainingMs, error; `pressToTalk()`, `release()`, `sendText()`), `checkMicrophone()`; tested against a fake WebSocket and the stub server. **Done when:** a 3-minute push-to-talk viva completes in Chrome against `VOICE_PROVIDER=stub`.
- **CL-6 / CL-7:** streaming reply into TTS, hands-free with Silero; first-pass review of every PR within 2 h.

### Parth: faculty dashboard (thin screens on `useFacultyApi`)
- **PA-0 Screen map (tonight).** `frontend/src/faculty/README.md`: one table, one row per screen: route, endpoints used (from `docs/API.md`), data shown, actions. **Done when:** every endpoint in the faculty section of `docs/API.md` appears in a row.
- **PA-1 Login + viva list (P1).** `Login.tsx`, `VivaList.tsx`. Token login (checked with `GET /faculty/vivas`), list with title, counts by status. **Done when:** works against the mock and the seeded backend.
- **PA-2 Session list (P1).** `SessionList.tsx`. Filters: status, low-confidence, search; "load more" using `next_cursor`; badges for `needs_review` and `overridden`. **Done when:** filters change the list on the seeded backend.
- **PA-3 Session detail, read-only (P1).** `SessionDetail.tsx`. Transcript by `idx`; per-dimension score, reason, evidence chips that scroll to the turn; 3 run totals and spread; low-confidence reasons. **Done when:** a seeded scored session shows all of it.
- **PA-4 Audio replay (P2).** `AudioPlayer.tsx`. `<audio>` from `audio.url`; clicking a transcript turn seeks to its `t_start_ms`; the stereo recording is student left, AI right. **Done when:** clicking turn 5 plays from its offset.
- **PA-5 Actions (P2).** `ReviewActions.tsx`. Override (reason required, history list), review note, rescore. **Done when:** each action updates the screen and survives a refresh.
- **PA-6 Bank and roster (P3).** `BankUpload.tsx`, `RosterUpload.tsx`. Upload with per-row 422 errors; `ai-draft` badge and **Approve**; access codes shown once with a copy button. **Done when:** a bad file lists every row error.
- **PA-7 Export and release (P3).** CSV export button, release-results toggle. **Done when:** the CSV downloads and the toggle persists.

### Bhavesh: student screens, QA, demo (screens on `useStudentSession` and `useVoiceSession`)
- **BH-0 Flow and copy (tonight).** `docs/qa/student-flow.md`: each screen with its states and, for **every error code in `docs/API.md`**, the exact sentence a student sees (plain, kind, tells them what to do). **Done when:** every error code has a sentence.
- **BH-1 Student screens, text mode (P1).** `src/student/screens/`: `Join`, `RulesConsent`, `Waiting`, `Viva` (typed answer, countdown, error banner), `Done`. **Done when:** a full viva completes against the real backend with typing only.
- **BH-2 Voice on the viva screen (P1, after CL-5).** `Viva.tsx` uses `useVoiceSession`: press-and-hold button, state label (listening/thinking/speaking), live transcript, AI text, countdown, "type instead" fallback. **Done when:** a push-to-talk viva completes in Chrome.
- **BH-3 Mic check (P2).** `MicCheck.tsx` using `checkMicrophone()`: permission, level meter, clear failure messages. **Done when:** denied permission shows the fix steps.
- **BH-4 Browser test pass (P2).** Run `docs/qa/student-checklist.md` (Claude writes it with CL-4) in Chrome, Safari and Firefox; file each defect as a GitHub issue with steps and a screenshot. **Done when:** a filled-in checklist is in the PR.
- **BH-5 Demo script (P3).** `docs/DEMO_SCRIPT.md`: the 5-minute demo as numbered steps with what to say; then record it. **Done when:** Mayank can follow it cold.

### Tejas: evidence and data (Pro tools; unchanged scope plus two)
- **TJ-1 Consent and volunteers (today).** Fill every `<...>` in `docs/consent/consent_form_template.md` (retention: assume 1 month; providers: whisper.cpp, Piper, Ollama, Groq). **≥ 15 signed forms** (10 to be marked, 5 demo). Signed forms outside git; `docs/consent/register.csv` (volunteer ID, date, public-demo yes/no, no names).
- **TJ-2 Web Development question bank.** 30 questions like `config/question_bank.dsa.json` (24 concept, 6 applied, `source: "ai-draft"`) + CSV twin + a test copied from `test_question_bank_dsa.py`. **Done when:** the test passes and the API takes the upload with no warnings.
- **TJ-3 Clips and references.** ≥ 20 clips (≥ 10 Indian-accented technical English, ≥ 10 Hinglish) per `spikes/voice/RECORDING.md`; references in `evidence/wer/refs.csv`; audio on a shared drive, **not git**.
- **TJ-4 Clean-machine test (Wed night, again Fri).** Fresh clone, follow `README.md` only; file every snag as an issue.
- **TJ-5 Volunteers' vivas (Thu afternoon).** 10 volunteers on Mayank's Mac with `scripts/run_local.sh`; find a human marker for `docs/marking_sheet.csv`.
- **TJ-6 `scripts/wer.py`.** Port `spikes/voice/wer.py` and `bench_wer.py`; reads `evidence/wer/refs.csv`; writes `results/wer_*.csv` with a `.meta.json` sidecar; unit test.
- **TJ-7 `scripts/build_report.py`.** Generates the Test Report from `results/` (every row cites its file and sidecar; mock/stub/live labelled; nothing hand-typed). **Done when:** it runs on today's `results/` and produces a Markdown file.
- **TJ-8 `docs/PRIVACY.md`.** What is stored (audio, transcript, scores), where, who sees it, retention (assume 1 month), deletion on request, outside services.

## 7. Review protocol (Mayank's load about 1 to 1.5 h/day)
1. Author opens the PR from the template: what, how to run, screenshot or clip, **`npm run check` and `check_paths.py` output**, assumptions the AI listed.
2. Claude posts a first-pass comment (✅ / ❌ and exact fixes) within 2 h.
3. Mayank reviews in two windows a day (suggest 13:00 and 20:00 IST), about 10 min per PR: (a) gates green and pasted, (b) only owned paths, (c) demo matches "Done when", (d) no secrets or audio, (e) CREDITS line if a tool was added.
4. Merge order: CL-4 first, then everything else. Shared files (`frontend/src/api`, `docs/openapi.json`) change only through Claude.
5. A PR that fails the gates twice goes back to the card: Claude or Tejas splits it or takes it over.

## 8. Start prompt (paste into your AI tool; replace `<card>` and `<name>`)
> You are helping on the Voxam repo (`hub-mayank/ai-viva`). Read `docs/TEAM_PLAN.md` sections 5 and 6, card `<card>` only. Work only in the files named in the card; do not touch any other file and do not add dependencies. Use only the types in `frontend/src/api/schema.ts` and the hooks named in the card; if a field, endpoint or hook is not there, say so and stop instead of inventing it. Make the smallest change that meets "Done when". Then run `cd frontend && npm run check` and show me the output. Finally list every assumption you made and the file and line you relied on. Branch name: `feat/<name>-<card>`.

## 9. Risks and fallbacks
| Risk | Plan |
|---|---|
| CL-4/CL-5 late | Teammates do PA-0/BH-0 (paper work) first; M1 moves to Wed 18:00; P3 cards drop. |
| Free AI tool produces plausible but wrong code | Typed hooks and `npm run check`; Claude review; a card that fails twice is split or taken over. |
| Voice path slips | Ship push-to-talk only (Plan B in `docs/PLAN.md`). |
| Teammates cannot run whisper.cpp/Piper locally | `VOICE_PROVIDER=stub` is the default in `run_local.sh` when models are absent. |
| Evidence starts too late | Tejas's TJ-1..3 run now, independent of the prototype. |

## 10. Defaults used (tell me to change any)
Local-first = option A (local profile now, sync bundle later); Hindi/Hinglish: understand, interview in English; retention 1 month; review windows 13:00 and 20:00 IST; teammates are collaborators; frontend in React + Vite + TypeScript with plain CSS; no AI trailers in commits.

**Not editable here:** `docs/PLAN.md` is the Planner's. It still names "Friend A/B/C" and T6 as 3 days for one person; suggested edit: T6 owners Parth (dashboard) and Bhavesh (student pages), foundation and voice SDK by Claude (CL-4, CL-5), per this file.
