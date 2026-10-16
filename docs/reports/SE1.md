# SE1 scoring_error on failed sessions: 👍 done   (2026-10-17, CORE)
Stacked on `task/integrity-signals` (PR 78): both regenerate `docs/openapi.json`, so merge 78 first, then this.

- Changed: nullable `scoring_error` on `SessionDetail` and `SessionSummary`. When the status is `failed` it is one plain sentence chosen from the stored job error (model unavailable or over its limit; wrong format on every attempt; no answers; not ready; scores not saved; otherwise "unexpected reason"). The technical error stays in the worker log, because it can quote model output.
- Changed: one extra query per list page (jobs of failed sessions only), `docs/API.md`, `docs/CHANGELOG-api.md`, `docs/openapi.json`, `frontend/src/api/schema.ts`, Parth's brief (now uses the field).
- Evidence: `python -m pytest -q --ignore=backend/tests/test_voice_spike.py` -> `568 passed, 2 skipped`; `cd frontend && npm run check` -> `100 passed | 3 skipped`; `python scripts/check_secrets.py` -> `secret scan clean`. New: `backend/tests/test_scoring_error.py` (10).
- Not verified / not run: the field against the failed session on Mayank's machine (his database is not in the repo); the sentence matching a failure from every live provider (the mapping is by the start of the stored text; unknown text gets the generic sentence).
- Risks found: the mapping depends on the wording of the error strings in `scorer.py` and `services/scoring.py`; a changed string degrades to the generic sentence, not to a leak.
- Suggestions: none beyond Parth showing it (his PR 2).
- Questions for Mayank: none.
- Next task proposed: Groq fairness probe (blocked until the token window frees, see chat).
