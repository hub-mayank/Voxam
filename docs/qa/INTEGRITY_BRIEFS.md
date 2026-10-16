# Integrity signals: who does what

**Date:** 16 Oct 2026 · Background: `docs/INTEGRITY.md` (read it first, five minutes) and decision D27.

Why this exists: a web page cannot stop an overlay tool such as Cluely, and we must not claim it can. We add three honest layers:
the student page reports tab switches and paste/copy, the rules text says so, and the interviewer asks one cross-check question.
Claude built the backend (endpoint, rules text, cross-check, tests, docs). Three pieces are left, one each.

**Order:** merge Claude's PR first (it regenerates `docs/openapi.json` and `frontend/src/api/schema.ts`). Bhavesh and Parth rebase on it.
Bhavesh does his integrity PR **after** his viva-screen UX PR (PR 3 of his brief) so they do not collide in `Viva.tsx`.

---

## Bhavesh: report the signals from the viva page (about half a day)
**Paths:** new `frontend/src/student/integrity/`, one line in `student/screens/Viva.tsx`, one function in `student/` API client. Nothing else.

API (already live): `POST /student/sessions/{sid}/integrity` with `{ events: [{ kind, duration_ms?, chars?, client_id? }] }`, 1-20 events per call.
Kinds: `tab_hidden`, `window_blur`, `paste`, `copy`. Returns `{ recorded }`. See `docs/API.md`.

Build `useIntegritySignals(sessionId, enabled)`, enabled only while the viva is in progress (not on Join, Rules, Ready, MicCheck, Done):
1. **Tab hidden:** on `visibilitychange` to hidden remember the time; on visible, if away for 3 s or more, send `tab_hidden` with `duration_ms`. Under 3 s: send nothing.
2. **Window blur:** on `blur` remember the time; on `focus`, if the tab was never hidden in between and the window was away for 3 s or more, send `window_blur` with `duration_ms`. (Switching tabs fires both events; send only `tab_hidden`.)
3. **Paste:** `paste` event anywhere on the page: send `paste` with `chars` = length of the pasted text. **Never send the text.**
4. **Copy:** `copy` event: `copy` with `chars` = length of the selection. Never the text.
5. Each event gets `client_id` = a short random string (e.g. `crypto.randomUUID().slice(0, 8)`), so a retry is stored once.
6. Fire and forget: no spinner, no error message, no blocking. One retry after 5 s on a network error; drop on any 4xx. Keep at most 20 unsent events.
7. Do not stop the student from pasting or copying. We only note it.
8. Show one muted line on the viva screen: "Tab changes, paste and copy are noted for faculty review. They do not change your mark."

Tests (vitest, fake timers): short absence sends nothing; 5 s hidden sends one `tab_hidden` and no `window_blur`; blur-only sends `window_blur`; paste sends only a length (assert the request body contains no text); failure is swallowed; nothing is sent when `enabled` is false; listeners are removed on unmount.
Done when: `npm run check` green, tests above, and Tejas's browser sheet (below) passes in Chrome and Safari.

---

## Parth: show the signals and the cross-check to faculty (about half a day)
**Paths:** `frontend/src/faculty/` only. Build on top of your session-detail PR 1 (summary card) if it is merged; otherwise add it to the current layout.

Data already in `GET /faculty/sessions/{sid}`: `integrity_events[]` = `{ id, kind, t_ms, detail }` where `t_ms` is the viva clock in milliseconds, and `detail` has `duration_ms` or `chars`. Turns have `action` and `question_id`.
1. **Signals section** on the session detail (below the summary card): heading "Signals to look at", one muted line "These are facts for you to weigh. They do not affect the mark."
2. Summary line: "3 signals: 2 tab hidden (19 s away), 1 paste (312 characters)". With none: "No signals recorded."
3. Timeline list, oldest first: time as `mm:ss`, a plain label ("Tab hidden", "Window lost focus", "Pasted text", "Copied text"), the detail ("away 9 s", "312 characters"). Use the neutral `info` badge, **not** red or warning colours: these are not verdicts.
4. For voice sessions each row has "Play from here", which seeks the audio to `t_ms / 1000`. Say in a tooltip that the position is approximate (a few seconds). For text sessions no button.
5. In the transcript, an AI turn whose `action` is `cross_check` gets a small badge "Cross-check" and a tooltip "Asked once, from something the student said in the opener".
6. Show the signal count in the summary card as an `info` badge so a reviewer sees it without scrolling. Do not add it to the sessions table (the list API does not carry it).
Tests: signals rendered in order, empty state, no red styling classes used, seek called with `t_ms / 1000`, cross-check badge only on that action.
Done when: `npm run check` green and a screenshot of a session with signals (use a hand-built mocked response) at both widths.

---

## Tejas: browser check and cross-check quality (about half a day)
No code. Needs Bhavesh's PR running (ask Mayank to tell you when).
1. Fill in `docs/qa/integrity-browser-check.md` on Chrome and Safari (text mode, then voice mode). Write what you saw, including what did not fire.
2. On every volunteer viva you attend, copy the cross-check line (the AI turn with the "Cross-check" badge, or the one after the first depth question) into `docs/qa/integrity-cross-check-log.md` with: the opener answer (one line), the AI's cross-check question, whether it made sense (yes / odd / wrong), and the student's reaction in a few words. Hinglish openers especially: does the English question still refer to something real?
3. Tell Mayank any question that sounded unfair, confusing, or revealed an answer. Those decide whether the prompt needs changing.

---

## Claude (done in this PR, for context)
`POST /student/sessions/{sid}/integrity` (stored with the server's clock, never the text, deduplicated, limited to 200 per session, ignored outside a running viva); rules text `rules-v2` for new vivas; interviewer `interviewer-v3` with one cross-check at the start of the depth phase, rebuilt from stored turns after a restart; tests; `docs/INTEGRITY.md`; decision D27; API docs and changelog.
