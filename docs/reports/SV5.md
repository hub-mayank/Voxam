# SV5 Broken-English fix attempt (scorer-v4 retry, filler strip): ⚠️ partial   (2026-10-19, CORE)
The prompt line (`scorer-v4`) does not help. Stripping spoken fillers from the model's input does, on the probe, but the probe is in-sample for that fix. Shipped prompt stays `scorer-v3`; the filler strip is new code in `scorer.py`.

- Changed: `strip_fillers()` in `backend/app/scorer.py`, applied to student turns in the model's input only (after `neutralise()`); it drops "um", "uh", "er", "erm", "hmm" and a "like" that directly follows one. The stored transcript and the faculty view are unchanged. Test added in `backend/tests/test_scorer.py` (real words such as "algorithm", "human", "umbrella" and "I like hash tables" are left alone).
- Evidence (all live, Groq `gpt-oss-20b`, `provider=live`, mean of 3 scorer runs per probe, scripted rewrites of the strong persona; identical content in correct English scores 100):
  - `scorer-v3`, no strip (`results/fairness_groq_gpt-oss-20b_mixing_v3_n3.csv`): Hinglish words 95.33 pass, broken English **88.0 fail** (depth 3.67).
  - `scorer-v4` (v3 plus one language line; `results/fairness_groq_gpt-oss-20b_mixing_v4_n3.csv`): Hinglish words 96.33 pass, broken English **87.67 fail** (depth 3.67). The earlier baseline validation failure did not repeat, so it was a flaky run; the prompt line gives no gain.
  - `scorer-v3` plus filler strip (`results/fairness_groq_gpt-oss-20b_mixing_v3_fillerstrip_n3.csv`, sidecar sha `d910ab2+dirty`: run before the commit, the committed diff is the same): Hinglish words 96.33 pass, broken English **93.67 pass** (depth 4, communication 4.33).
  - `python -m pytest -q --ignore=backend/tests/test_voice_spike.py` -> `569 passed, 2 skipped`; `python scripts/check_secrets.py` -> `secret scan clean`.
- Not verified / not run:
  - **In-sample.** The probe's rewrite inserts "uh like" every sixth word, and the strip was written knowing that. It shows the strip works on that pattern, not that real broken English is scored fairly. Real fillers in Whisper output (does it keep "um"/"uh"?) and real non-fluent speakers are untested; Tejas's clips are the check.
  - Dropped articles still cost some marks (depth 4 of 5 here); only fillers were addressed.
  - Not re-run: injection, off-topic and consistency probes with the strip (it only removes filler words).
- Risks found:
  - **The weak baseline moved a lot between runs** on the same model and prompt: 28, 34, 35 and 9 in four runs (2 scorer runs each). Injection and off-topic pass marks are set relative to it, so those results are less stable than they look, and so is any single AI mark. Another reason the human override and the marker comparison matter.
  - Roughly 59k Groq tokens used in the last 24 h.
- Suggestions: (1) keep `scorer-v3` plus the strip and say plainly in the test report that the broken-English gap was reduced on a synthetic probe and not shown on real speech; (2) ask Tejas to include 2-3 non-fluent but correct volunteers; (3) re-run the full fairness suite once on the final scorer before submission.
- Questions for Mayank: none.
- Next task proposed: re-run the full fairness and consistency probes on the final scorer (about 60k tokens), after the volunteer vivas.
