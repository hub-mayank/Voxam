# T1b Live baseline: ⚠️ partial   (2026-10-14, CORE work run from the VOICE worktree)
First live scorer evidence. Model: Groq `openai/gpt-oss-20b` (free tier, inside the call cap Mayank approved). **Scripted personas only: this shows the pipeline works on a live model, not accuracy against human marks (T8).**

- Changed: scorer prompt `scorer-v1` -> `v2` (feedback is 3-5 objects, no blanks; cite student turns only) -> `v3` (Hinglish is understood first, content scored on meaning); `scorer.tidy()` drops blank feedback entries before validation; `scripts/consistency.py` records a failed run instead of aborting. v1 and v2 files kept (a test pins every prompt hash).
- Evidence (all `provider=live`, sidecars with git sha, clean tree):
  - `results/bench_groq_gpt-oss-20b_scorer-v1.csv`: **FAIL as shipped**: 3 of 4 personas failed validation (empty strings padding `feedback`, and a cited AI turn). Kept as the before.
  - `results/bench_groq_gpt-oss-20b_scorer-v2.csv` (4 personas x 3 runs): strong 100.0, weak 28.0, idk 0.0, injection 8.0 (spread 30: runs disagree, so the confidence flag fires). Heuristic **PASS**.
  - `results/consistency_groq_gpt-oss-20b.csv` + `_summary.csv` (v2, 5 transcripts x 5 runs, 0 failed runs): strong 100 (sd 0), weak 26.8 (sd 3.3), idk 0, injection 10.2 (sd 7.4, range 20), **strong_hinglish 88.4 (sd 5.5)**.
  - **Fairness finding:** under v2 the Hinglish version of the strong answer lost 1 point on Conceptual and Depth in 4 of 5 runs, which the prompt forbids. Under v3 (`results/consistency_groq_gpt-oss-20b_hinglish_v3.csv`) it is 95.0 (sd 4.5): Conceptual 5 in 5 of 5 runs, Depth 5 in 3 of 5. **Better, not fixed.**
  - `results/bench_groq_gpt-oss-20b_scorer-v3_1run.csv` (v3, 1 run per persona): strong 100, weak 33, idk 0, injection 20: heuristic PASS.
  - `python -m pytest -q --ignore=backend/tests/test_voice_spike.py` -> see the final line in the PR; `python scripts/check_secrets.py` -> clean.
- Not verified / not run:
  - v3 was run once per persona (and 5x on Hinglish), not 3-5x on all: the Groq 200k tokens/day cap (we used 157k of the 180k the budget allows) ended the day's runs. Re-run `consistency.py --runs 5` after the 24 h window rolls.
  - Accuracy against human marks (needs B7 marker + `scripts/compare.py`), Gemini as scorer, the 3-run median pipeline on a live model through the worker.
- Risks found:
  - The same model gave a perfect 100 to the strong persona in every run: the strong persona may be too easy to separate high scorers; a rubric with only 5/5 at the top will compress real students. Needs the human-marked set.
  - Latency p95 56 s per persona is the 3-run scoring plus the 8k tokens/minute window; scoring 350 vivas on Groq alone is token-bound (as T5 computed).
  - Injection spread 30 shows one run partly followed the injected instruction; the flag catches it, the mark itself still moves.
- Suggestions: use the 120b model or Gemini flash-lite as scorer and Groq 20b as the live interviewer, then compare on `strong_hinglish` and `injection` (about 40 calls, one day of budget).
- Questions for Mayank: none blocking.
- Next task proposed: T9 cost and capacity (needs prices from you or a web lookup, ask-first), or T8 once clips and a human marker exist.
