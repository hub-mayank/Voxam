# INT1 Integrity signals and cross-check: ⚠️ partial   (2026-10-16, CORE)
Backend, rules text, interviewer cross-check, tests and docs are done and green. The student-page capture (Bhavesh) and the faculty display (Parth) are briefed but **not built**, so no signal is recorded from a real browser yet. Nothing here proves detection of any cheating tool; see `docs/INTEGRITY.md`.

- Changed: `POST /student/sessions/{sid}/integrity` (kinds `tab_hidden`, `window_blur`, `paste`, `copy`; server viva time; length only; dedupe by `client_id`; 200 per session; ignored outside `in_progress`), schemas, stub, `docs/openapi.json`, `frontend/src/api/schema.ts`, `docs/API.md`, `docs/CHANGELOG-api.md`.
- Changed: rules text `rules-v2` for new vivas (`rules-v1` kept, so existing vivas and their consent stay valid); tests now use `RULES_VERSION` instead of a hard-coded string.
- Changed: interviewer `interviewer-v3`: one code-owned cross-check at the first depth question, model-phrased from the student's opener (fixed fallback line if the model fails), skipped when the opener has fewer than 8 words; rebuilt from stored turns. No phase timing, rubric or weight changed. Also fixed `restore()` so a closing `move_on` credits its topic (found by the restore test once the cross-check changed the run).
- Changed: `docs/INTEGRITY.md`, D27, a `docs/PRIVACY.md` row, `docs/qa/INTEGRITY_BRIEFS.md` (Bhavesh, Parth, Tejas), `docs/qa/integrity-browser-check.md`, `docs/qa/integrity-cross-check-log.md`.
- Evidence: `python -m pytest -q --ignore=backend/tests/test_voice_spike.py` -> `558 passed, 2 skipped`. `python scripts/check_secrets.py` -> `secret scan clean`. `cd frontend && npm run check` -> `100 passed | 3 skipped` (schema regenerated). New tests: `backend/tests/test_integrity.py` (7), three in `backend/tests/test_restore.py`.
- Spot check (not recorded in `results/`, so no number is quoted): the cross-check prompt was run once on four openers on the local `llama3.2:3b`. With the first wording the model asked about things the student never said; the shipped wording stayed on what they said in three of four, and in one it named a service (an API) the student had not mentioned. An instruction hidden in an opener was ignored. Not tried on Groq (token window closed) or on a Hinglish opener beyond one line.
- Not verified / not run: any browser event (Chrome, Safari); voice mode with the cross-check (TTS: the model-written line is streamed and so not cached, same path as follow-ups; the fixed fallback line is cacheable); the cross-check on `gpt-oss-20b`; any effect on marks or interview quality; persona and load runs after `interviewer-v3` (they still say v2 in old results).
- Risks found:
  - Signals are noisy and a human has to weigh them. Wording in the rules text and in the faculty brief says so; if the faculty UI colours them as warnings, honest students are harmed.
  - A tool that hears the whole conversation can answer the cross-check; it helps a reviewer and does not block anything.
  - A small model can invent a detail in the cross-check question. A wrong premise would look unfair to the student. Needs Tejas's log from real vivas before the finals.
  - `interviewer-v3` changes the question order at the start of depth for every viva; results from before this change are not comparable on that point.
- Suggestions:
  - Record the cross-check outputs for the 10 volunteer vivas (the log file) and decide on evidence whether to keep it, tighten the prompt, or ask a fixed question instead.
  - Add `integrity_count` to the session list so faculty can sort by it; needs an additive API field.
  - For the pilot, run vivas in the maclab with a person present: it is the only real prevention.
- Questions for Mayank: this adds an API operation and changes interview behaviour (cross-check, `interviewer-v3`). Merge?
- Next task proposed: Bhavesh's `useIntegritySignals` PR, then Parth's signals section.
