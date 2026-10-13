# T4 / V2b live-LLM latency through the real voice server (Groq): ⚠️ partial   (2026-10-13, VOICE)
Repeats V2's end-to-end measurement with the intended live LLM (Groq `openai/gpt-oss-20b`, `reasoning_effort=low`, approved by Mayank, 59 calls per run). It found and fixed a real latency bug (fixed request spacing in the call budget). The result is under the 4 s Plan B trigger but **not** under the 2.5 s goal. Branch `task/T4-v2b-groq-latency`.

- Changed: `backend/app/llm/budget.py` (a sliding per-minute window instead of fixed 60/rpm spacing: a classify+phrase burst is no longer delayed), tests, `scripts/telemetry_tokens.py`, `scripts/free_tier_capacity.py` (`--call-tokens-source`), results below.
- Evidence (push-to-talk, 34 synthetic macOS voices cycled, whisper.cpp base + Piper alba, one student, server-measured; files in `results/`, `provider=live`, clean tree):

| run | n | server latency p50 | p95 | max | Groq phrase call p50 |
|---|---|---|---|---|---|
| fixed spacing (the T1c budget) `voice_e2e_local_groq_strict_pacing.csv` | 40 | 2.88 s | 4.33 s | 5.97 s | 2.07 s |
| sliding window (this branch) `voice_e2e_local_groq.csv` | 40 | **1.38 s** | **3.04 s** | 3.21 s | 0.49 s |
| (V2, local Ollama 3B, for comparison) | 39 | 1.00 s | 4.15 s | 4.83 s | n/a |

  - **Cause:** the registry spaced Groq calls 60/30 = 2 s apart, so the phrase call right after a classify waited about 1.6 s. A sliding minute window allows floor(0.9 x 30) = 27 calls a minute with no spacing; the provider's limit is per minute, so 429 risk is unchanged.
  - **Tokens per call, measured** (`results/groq_interview_tokens.csv`, 118 calls): mean 267 (classify 291, phrase 220, max 333) against the 400 assumed in T1c. Interview-token capacity moves from 450 to 674 calls/day/model (Groq tpd-bound): about 42 vivas interviewed per day per Groq model, 25 students at once (tpm-bound); scoring tokens are still an assumption (`results/free_tier_capacity.csv`, basis column says which is which).
  - Budget accounting: 118 Groq calls counted in 24 h (cap 150 global, 900 for the model).
  - Tests: `python -m pytest -q --ignore=backend/tests/test_voice_spike.py` -> 458 passed, 2 skipped.
- Not verified / not run: real people's speech; more than one student at a time (a second student's call would share the same minute window: 27 calls/min per model is about 5 simultaneous vivas at this call rate, the capacity table says 25 by tpm: **the rpm window, not tpm, is the tighter limit** and the capacity script does not model it yet); streaming of the phrase into TTS; the viva did not end within 40 answers (the run measures turns, not completion); Gemini as a second chain entry; scoring on a live model.
- Risks found:
  - **Concurrency is rpm-bound, not tpm-bound:** 30 rpm x 0.9 = 27 calls/min; one viva makes about 1.41 calls per answer, one answer about every 20-30 s, so one Groq model carries only about 6-10 simultaneous vivas before calls start waiting or falling through to the next chain entry. The earlier "28 students at once" came from a per-viva *average* rate; bursts of simultaneous answers are worse. `scripts/free_tier_capacity.py` should take the per-minute window into account.
  - p95 3.04 s: the tail turns are the phrase turns (STT ~0.35 s with process start, classify ~0.46 s, phrase ~0.49 s, Piper on text that is not cached 0.2-0.4 s).
- Suggestions: (1) stream the phrase into TTS and start Piper on the first sentence (about -0.3 to -0.8 s on phrase turns); (2) a persistent `whisper-server` (about -0.1 s per answer); (3) run classify and the bank-question TTS lookup in parallel with STT of the next answer is not possible, but **prefetch the next bank question audio** is already free (cached); (4) model the rpm window in the capacity script and put a second Groq model (`gpt-oss-120b`, same limits) or Gemini Flash-Lite in the chain for bursts; (5) correct the "28 at once" claim in D19's risk text.
- Questions for Mayank: none blocking. Push `task/T4-v2b-groq-latency`.
- Next task proposed: V3 (hands-free with Silero VAD + pre-roll, reply streaming), after CL-5 lands with Bhavesh.
