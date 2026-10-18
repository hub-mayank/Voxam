# FP1 Broken-English fairness recheck on Groq: ⚠️ partial   (2026-10-18, CORE)
`scorer-v3` (shipped) still loses content marks on broken English; `scorer-v4` (candidate) cannot be used. Nothing changed in the code.

- Changed: results only (`results/fairness_groq_gpt-oss-20b_mixing_v3*.csv` and sidecars). No code, prompt or config change.
- Evidence (live, Groq `gpt-oss-20b`, `provider=live`, scripted transcripts from the strong persona, sidecar sha `607eb2a`, whose scorer files equal `main`):
  - `python scripts/fairness_probes.py --llm groq:openai/gpt-oss-20b --live --only mixing_ --tag groq_gpt-oss-20b_mixing_v3` (1 run per probe): Hinglish words 93.0 and broken English 91.0, both pass; strong baseline 100.0.
  - Same with `--probe-runs 3 --tag groq_gpt-oss-20b_mixing_v3_n3` (mean of 3): Hinglish words **95.33, pass**; broken English **88.0, fail**: conceptual 5, depth 3.67, problem 4.67, practical 5, communication 3, against 5/5/5/5/5 for the same content in correct English. The pass rule allows a loss of at most 1 point on a content dimension; depth lost 1.33.
  - `scorer-v4` (run through a wrapper that selects it for one run): the baseline itself failed validation ("evidence turns not student turns/nonexistent" on every attempt), so no probe ran and no result file exists. v4 stays unselected.
- What this means: the earlier single failure (86.0) was not a fluke and the single-run pass (91.0) was not a fix; with 3 runs the average still loses about 12 total points for identical content. Part of that is the communication dimension (3 of 5), which is arguably a fair reading of unclear English and is outside the rule's content check; depth is the real fairness problem.
- Not verified / not run: more than 3 runs; `scorer-v4` beyond its baseline validation failure; the speech-filler strip mentioned in T8 (not part of this run); other models; real spoken broken English (these are scripted rewrites of one persona).
- Risks found: a student who answers correctly in non-fluent English can lose about 10 points. The human override and the marker comparison are the safeguards for the finals; this must be said in the report rather than hidden.
- Suggestions: (1) keep `scorer-v3`, state this gap in the final test report with the two result files; (2) try a v4 that keeps v3's evidence-citation rules and only adds the language instruction, and re-run with `--probe-runs 3` (about 20k tokens); (3) have the human markers rate a few non-fluent but correct volunteer vivas, so the gap is measured on real speech.
- Questions for Mayank: none.
- Next task proposed: v4 retry (suggestion 2), or the volunteer vivas.
