# STATUS (Planner-owned baseline; task reports live in `docs/reports/`)

## 2026-10-07: baseline before handoff
**Done (offline, mock LLM):** config-driven phases + rubric (validated), code-owned clock, follow-up policy, interviewer with audit-log events, text CLI, scorer (JSON rubric, evidence validation, 3-run median, low-confidence flags), persona fixtures (strong/weak/idk/injection; regenerate with `scripts/make_personas.py`), `scripts/compare.py`, `scripts/bench_models.py`, `app/list_models.py`. 24 tests passing (`python -m pytest` from the repo root).

**Verified live (2026-10-06):** Gemini adapter works with `gemini-3.5-flash`. Strong persona 100/100, weak 28/100, 3 runs each, spread 0 (valid fixtures). Scorer call latency p50 6.1 s, p95 9.3 s (long prompt; not the live-interview path).
**Not measured live:** idk and injection personas (quota hit), interviewer classification quality, any live-path latency.

**Provider facts (2026-10-06, re-verify before relying):**
- `gemini-2.5-flash`: 404 "no longer available to new users". `gemini-2.5-pro`: 404 (reason not captured).
- `gemini-3.5-flash`: free-tier quota 20 requests/day. `gemini-3.8-flash`: 503 high demand. `gemini-3.5-flash-lite`: timed out.
- An earlier benchmark run was invalid (fixture bug, one answer repeated for every question). Fixed.

**Repo:** `github.com/hub-mayank/ai-viva`, branch `main`, 2 commits (Step 1, Step 2). Step 3 files (fixed personas, `make_personas.py`, `bench_models.py`, `pytest.ini`, hardened `gemini.py`, `scorer.py` token change, `results/`) were uncommitted at handoff. Mayank commits them before any Claude Code session starts. `results/bench_20261006_012904.csv` is from the INVALID run (quarantine in T0).

**Never run / unverified:** `docker-compose.yml`, `db/schema.sql`, any voice component, API, dashboard, load behaviour, Hinglish.

**Known gaps:** no persistence; clock is in-process and not restart-safe; 90 s answer cap not enforced; no telemetry; no call-budget guard; no secrets scan; adapter has no retry (only the bench wrapper does); sample question bank too small (5 concept / 2 applied; need ≥7 / ≥3).

**Open:** blockers B1-B8 in `PLAN.md`; decisions in `DECISIONS.md`.
