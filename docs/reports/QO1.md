# QO1 Difficulty-aware question order: 👍 done   (2026-10-19, CORE)
- Changed: `Interviewer._pick` in `backend/app/interviewer.py` now picks fundamentals questions from difficulty 1-2 and depth questions from 2-5, falling back to the whole pool when the band is empty (D28). Applied questions are unbanded. Three tests in `backend/tests/test_restore.py`.
- Evidence: `python -m pytest -q --ignore=backend/tests/test_voice_spike.py` -> `571 passed, 2 skipped` (includes the restore tests, which prove a rebuilt interviewer picks what the live one did).
- Not verified / not run: effect on real vivas or on scores; the two shipped banks have 8 and 7 difficulty-1 and 13 and 12 difficulty-2 concept questions, so the bands are never empty for them (from `python scripts/check_bank.py`).
- Risks found: a bank with few easy questions silently falls back to any difficulty; `scripts/check_bank.py` now says so ("only N concept questions of difficulty 1-2"). Earlier persona and follow-up results used random order and are not comparable on question order.
- Suggestions: after the team vivas, look at whether the first two questions felt appropriately easy (add a column to `docs/qa/integrity-cross-check-log.md` if useful).
- Questions for Mayank: merge? It changes interview behaviour for every viva (spec-adjacent: no timings, rubric or weights touched).
- Next task proposed: question banks (this evening).
