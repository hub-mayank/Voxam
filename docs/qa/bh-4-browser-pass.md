# BH-4 browser pass — partial browser run (2026-10-16)

`docs/qa/student-checklist.md` is the run sheet for the full browser
pass. This file includes the earlier code-review-only trace and the
partial local browser run recorded below. The required full browser
run is still outstanding — see "What the human browser run still has
to prove".

The partial results below are browser evidence only for the exact
screens, browsers, and viewport sizes named. They do not satisfy the
full matrix, and unrun checklist rows remain open.

## Partial browser results

Run against the local seeded `local-dsa` viva on 2026-10-16. No
production student data was used.

- **Chrome, dark, desktop default (1633×865 CSS px):** completed Join,
  accepted Rules, Ready, started a typing viva, submitted answers, and
  reloaded during the viva. The server restored the current question
  and the log displayed “Earlier answers are saved.” No duplicate
  answer was observed.
- **Chrome, dark, Viva at 390×844 CSS px:** the text-viva screen fit
  with no horizontal document overflow (`scrollWidth` 390 px).
- **Chrome, dark, Viva at 1280×800 CSS px:** the text-viva screen fit
  with no horizontal document overflow (`scrollWidth` 1280 px).
- **Safari, dark, desktop:** reached the Rules screen from Join. The
  full student flow was not completed.
- **Chrome, light, desktop:** visually inspected the text-viva screen;
  this was not a full light-theme flow review.

No reproducible defect was observed in those partial checks, so no
failure issue was filed. The Done screen, all six screens at both
requested widths, the remaining browsers, and the voice and resilience
scenarios were not verified in this run. No microphone permission was
granted.

The row-by-row table below remains a **code-review-only** trace. The
browser observations above are not upgrades to that table's verdicts.

## Scope required by docs/qa/BHAVESH_REPLY.md

The human run must cover:

- Browsers: Chrome, Edge, Safari, Firefox (Edge is additional to
  the old checklist's Chrome / Safari / Firefox).
- Voice on at least 2 browsers.
- The old 13 checklist rows, PLUS 4 extra scenarios:
  1. Backgrounded tab at timer expiry.
  2. 5 consecutive sessions.
  3. Offline during an answer.
  4. Phone-width layout (already row 13; run it explicitly as a
     named scenario, not as an afterthought).
- Commit the filled results. File one issue per failure, with
  steps, expected, actual, and a screenshot.

## How the old pass was done (and why its refs are superseded)

The old pass read the BH-1–BH-3 screens on local branches and
checked each checklist expectation against the code path serving
it. Those screens have been replaced by main's student flow.
Therefore:

- All file / line references in the old BH-4 note are SUPERSEDED.
  Do NOT cite them as current. They pointed at screens that no
  longer exist on main.
- The rows below are mapped to main's ROUTES, not to old files:
  `/student` (Join, `?viva=`), `/student/rules` (RulesConsent),
  `/student/ready` (Ready screen), `/student/mic-check`
  (MicCheck), `/student/viva` (router, `?mode=`), `/student/done`
  (Done). The router renders separate text / voice viva
  components; their file paths are NOT stated here because they
  were not verified — do not invent them.
- Every verdict below is "code-review only; needs browser".

## Row-by-row (code-review only — verdicts are not browser results)

| # | Checklist step | Main route / what to prove | Verdict |
|---|---|---|---|
| 1 | Join with `local-dsa` / `LOCAL01` / printed code | `/student?viva=local-dsa` — Viva ID + student ID + access code → rules screen | Code-review only; needs browser |
| 2 | Wrong code | `/student` — kind, specific message; no crash; wait time shown after repeated tries | Code-review only; needs browser |
| 3 | Decline the rules | `/student/rules` — nothing starts | Code-review only; needs browser |
| 4 | Accept, press Start | `/student/rules` → `/student/ready` → Start → first question, countdown starts near 15:00 | Code-review only; needs browser |
| 5 | Type an answer, send | `/student/viva?mode=text` — AI reply appears; countdown keeps running | Code-review only; needs browser |
| 6 | Reload the page mid-viva | `/student/viva` — same question and time left; no duplicate answer | Code-review only; needs browser |
| 7 | Network off, send, on, send again | `/student/viva` — one answer stored; no duplicate | Code-review only; needs browser (airplane-mode toggle) |
| 8 | Clock reaches 0 | `/student/viva` — closing message; no more input | Code-review only; needs browser (full 15-minute wait, or a short test viva if the backend allows one) |
| 9 | Mic check, deny permission | `/student/mic-check` — plain fix steps; typing still works | Code-review only; needs browser |
| 10 | Mic check, allow | `/student/mic-check` — level meter moves when you speak | Code-review only; needs browser (real microphone) |
| 11 | Voice answer (push-to-talk) | `/student/viva?mode=push_to_talk` — live transcript, AI speaks, state label changes | Code-review only; needs browser (real microphone) |
| 12 | Speak while the AI is talking | `/student/viva?mode=push_to_talk` — the AI stops and listens (barge-in) | Code-review only; needs browser — see F1, must re-verify |
| 13 | Narrow window to phone width | All 6 screens — nothing overlaps; buttons reachable | Code-review only; needs browser (resize + touch targets) |
| 14 | Backgrounded tab at timer expiry (NEW) | `/student/viva` — background the tab, let the clock run out, return: closing message, no more input, no extra time | Not covered by old pass; needs browser |
| 15 | 5 consecutive sessions (NEW) | `/student` → `/student/done` × 5 — each session clean, no state leaking into the next | Not covered by old pass; needs browser |
| 16 | Offline during an answer (NEW) | `/student/viva` — go offline mid-answer, reconnect, resend: one answer stored, no duplicate | Not covered by old pass; needs browser |
| 17 | Phone-width layout as a named scenario (NEW) | All 6 screens at phone width — same bar as row 13, run explicitly | Not covered as a named scenario; needs browser |

Mic check is skipped for text and required before voice. Demo /
test the voice rows with `?mode=push_to_talk` (and, where the
human run covers it, `?mode=hands_free`).

## Old findings — MUST re-verify on main, do NOT assume they persist

The old BH-4 note fixed two Viva defects (F1, F2) and listed three
gaps (G1–G3) on the OLD screens. Main's flow differs. All five
must be re-verified against main's current components before
anyone claims them as fixed or open:

- **F1 — barge-in was impossible on the old Viva.** Old cause: the
  hold-to-talk control was disabled while the AI was speaking.
  Old fix: enable it while listening AND speaking. Re-verify
  against main's voice component — main may already handle
  barge-in. If it still fails on main, file an issue; do NOT
  fix shared voice code directly (see below).
- **F2 — typed answers after voice could hit `bad_client_seq`
  on the old Viva.** Old cause: voice answers advanced the
  server's answer count without updating the HTTP session's
  counter. Old fix: re-read status when the voice socket closes.
  Re-verify on main; file an issue if it still reproduces.
- **G1 — no status polling in the session hook (old).** Re-verify
  on main. If still true, file an issue — session code is shared
  (Claude-owned), not a Bhavesh direct fix.
- **G2 — no `result()` on the session hook (old).** Re-verify on
  main. Main's Done shows closing words + Sign out, no score, so
  the result pattern is still unsettled. File an issue if the
  pattern is still unblessed — do not invent one.
- **G3 — hands-free not offered (old).** Re-verify on main.
  Main's router already accepts `?mode=hands_free`, so G3 may
  be resolved or may need a UI path to select it. Do NOT assume
  either — check the live UI, then file an issue if the mode
  cannot be reached from the student flow.

Per `docs/qa/BHAVESH_REPLY.md`: file issues for shared
session/voice defects — do NOT fix them directly.

## What the human browser run still has to prove

Rows 7, 8, 10, 11, 12, 13, 14, 15, 16, 17 cannot be proven by
reading code: real microphone permission flows, real audio
playback / interrupt, the network toggle, the 15-minute deadline,
a backgrounded tab at expiry, 5 back-to-back sessions, offline
during an answer, and phone-width layout all need a browser.
Run `docs/qa/student-checklist.md` top to bottom in Chrome,
Edge, Safari and Firefox, with voice on at least 2 browsers;
every failure becomes a GitHub issue with steps, expected,
actual and a screenshot.

## Relationship to other docs (do not duplicate)

- **`docs/qa/student-checklist.md`** is the run sheet. This note
  is NOT a substitute for it — the human fills the checklist
  columns; this note only records what was traceable in old
  code.
- **`docs/reports/browser-pass-BH-4.md`** (if it exists on main):
  local branch contents contain NO such file, so its existence
  / contents on main were not verified here. If main has one,
  this note is NOT a duplicate of it: this note is the
  code-review-only precursor (old screens, unverified); the
  reports file, if present, is the authoritative pass record.
  Cite the reports file for browser results and this note only
  for what was traceable in old code. Do not merge the two.
  If main has no such file, this note stands alone as the
  code-review-only record.
- **`docs/qa/BHAVESH_REPLY.md`** governs the browser-pass scope
  (browsers, voice coverage, extra scenarios, commit results,
  issue per failure) and the issues-not-direct-fixes rule.
  Where this note and that note disagree, that note wins.
- **`docs/qa/student-flow.md`** governs wording/copy. This note
  makes no wording claims — wording deltas live in the BH-0
  port, not here.

## Left out (intentionally) + why

- Old file / line references (e.g. old `Viva.tsx`, `MicCheck.tsx`,
  `useStudentSession.ts`, `useVoiceSession.ts` lines). The old
  screens were replaced by main's flow; citing old refs as
  current would mislead. Rows are mapped to main's routes
  instead, and component file paths are not invented.
- Old F1 / F2 presented as "fixed". They were fixed on the OLD
  screens only. On main they are re-verify items, not done items.
- Any claim of a browser result (PASS/FAIL in a real browser).
  None was run. Every verdict here is code-review only.
- Implementation / API / protocol detail (hooks, `client_seq`,
  polling mechanics, WebSocket messages). That lives in
  `docs/SPEC.md` / `docs/API.md` / `docs/VOICE_PROTOCOL.md`,
  not in a pass note.
- Wording/copy sentences. Those belong to the BH-0 port
  (`docs/qa/student-flow.md`), not to this note.
