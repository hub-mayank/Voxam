# T4 / V3b reply streaming into TTS: ⚠️ partial   (2026-10-13, VOICE)
A model-phrased follow-up is now spoken sentence by sentence while the model is still writing it. It lowers the **local (Ollama) p95 from 4.15 s to 3.03 s** (turns over 2 s: 12 of 39 to 5 of 40; the single worst turn is unchanged at 4.83 s); on Groq it is expected to matter little (its phrase call is almost all first-token time) and **was not re-measured** (the 24-hour call cap, 118 of 150 used). Branch `task/T4-v3b-reply-streaming`.

- Changed: `generate_stream` on the Ollama and OpenAI-compatible adapters (budget and token accounting kept; Gemini does not stream and falls back to one piece at the end); `ResilientLLM.complete_text(on_delta=)` (retry and fallback until the first piece is out, then a failure is raised, never repeated); `GracefulLLM`/`MockLLM` pass-through; `Interviewer.respond(on_phrase_delta=)` and `StudentService.answer(on_phrase_delta=)` (only for a reply this call really produces, never a replay); `VoiceSession` streams finished sentences, then sends `ai_turn` with the final text and the remaining sentences, or on a mismatch (model died, canned reply) sends `interrupt` and speaks the real reply; protocol note.
- Evidence: `python -m pytest -q --ignore=backend/tests/test_voice_spike.py` -> **476 passed, 2 skipped**. New tests: Ollama NDJSON and OpenAI SSE adapters (pieces, final usage, token booking), the retry rule (before the first piece: fall back; after it: raise, no retry), canned line after a dead stream, and two session tests (audio of sentence one precedes `ai_turn`; a stream that dies midway is cut with `interrupt` and the real reply is spoken). End to end, push-to-talk, real whisper.cpp + Piper, Ollama llama3.2:3b, 34 synthetic clips cycled to 40 answers, server-measured:

| run | n | p50 | p75 | p90 | p95 | max | turns over 2 s |
|---|---|---|---|---|---|---|---|
| V2, no streaming (`voice_e2e_local_ollama.csv`) | 39 | 1.00 s | 2.69 s | 3.85 s | **4.15 s** | 4.83 s | 12 |
| V3b, streaming (`voice_e2e_local_ollama_streaming.csv`) | 40 | 1.01 s | 1.83 s | 2.17 s | **3.03 s** | 4.83 s | 5 |

  "Latency" is student stops speaking -> first AI audio. The text of a streamed reply (`ai_turn`) arrives later than the first audio, by the rest of the generation (client-side p95 until `ai_turn`: 3.95 s).
- Not verified / not run: Groq with streaming (expected small gain: its phrase call is 0.49 s total); Gemini (does not stream); a real microphone; real people; two sentences are only streamed when the model writes an end-of-sentence mark followed by a space (a one-sentence reply gains nothing); speaking while the first sentence plays (barge-in during streaming is covered by the same interrupt rules but has no dedicated test).
- Risks found:
  - Correction of my earlier claim: I called streaming "the biggest lever" for the live path. By the T3b numbers it is not for Groq (first sentence 0.45 s vs total 0.47 s); it matters for the local-first profile where the LLM is Ollama. What dominates on Groq is STT start-up (~0.4 s), two model calls (~0.46 s each, with a p95 near 1 s each) and uncached Piper.
  - A streamed first sentence is spoken before the whole reply exists; if the interviewer ever post-processes the reply (it currently only strips), the mismatch path (interrupt and re-speak) is the safety net.
  - One more provider-specific code path (`generate_stream`) to keep in line with `generate` (budget, retries).
- Suggestions: (1) For Groq: a smaller non-reasoning model for the classify call, or the second Groq model hedged in parallel, would cut the tail; both need a decision on models and a few live calls. (2) A persistent `whisper-server` (-0.1 s per answer). (3) Skip the classify call for answers the code can already label (empty, "I don't know").
- Questions for Mayank: push `task/T4-v3b-reply-streaming`. None blocking.
- Next task proposed: the voice-lab join form (so you can see all of this yourself), then T7 load-harness inputs.
