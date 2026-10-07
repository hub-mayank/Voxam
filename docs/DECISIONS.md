# DECISIONS (append-only; newest at the bottom; each change needs a new entry)

Format: **ID title.** Decision. Why. Status (`accepted | proposed | pending`). Date.

**D1 Engine is framework-independent; code owns the clock and policy.** The LLM only classifies answers and phrases replies. Why: fairness and auditability (same structure for every student), testability. Accepted. 2026-10-05.

**D2 Interviewer and scorer are separate.** Scoring runs after the session on the full transcript, 3 runs → median, prompt + rubric version stored. Why: the PDF requires it and the live path must stay fast. Accepted. 2026-10-05.

**D3 All providers sit behind adapters with telemetry; mock by default.** Live calls are opt-in and capped. Why: evidence (latency, cost, error rates) comes from telemetry; free-tier and budget protection. Accepted. 2026-10-07.

**D4 Model: provisional `gemini-3.5-flash` for both roles.** Pending a paid-tier benchmark of the candidates. `gemini-2.5-*` unavailable to new users (404, 2026-10-06). Why: the only model with valid results so far. Pending. 2026-10-07.

**D5 Dev DB SQLite; target Postgres via Docker Compose; scoring queue is DB-backed (`FOR UPDATE SKIP LOCKED`), not Redis.** Why: fewer moving parts; Docker not yet installed (B3). Risk: SQLite hides concurrency bugs, so the load test must run on Postgres. Proposed; Claude Code to confirm or replace in T2a. 2026-10-07.

**D6 Scale proof in two layers.** Stub providers at 50/100/150 (tests our orchestration, DB, memory); live providers at ≤20 (tests vendors and rate limits). Every results row labelled `provider=stub|live`. Why: free tier and no credits make a live 150 impossible. Risk: judges may discount stub results, and the report must say so. Proposed. 2026-10-07.

**D7 Voice stack undecided.** T3 spike measures candidates; decision by G1 (Oct 10). Why: latency is the biggest technical risk; PDF suggests LiveKit Agents or Pipecat. Pending. 2026-10-07.

**D8 Cost target ≤ ₹20 per viva is ours, not MSOT's.** MSOT only says ₹500 per student is not viable. Verify with real pricing (T9). Accepted as an internal target. 2026-10-07.

**D9 Hinglish.** STT must transcribe Hinglish well (the WER test needs ≥20 clips across Indian-accented English and Hinglish). Hinglish interviewing stays a stretch goal. Accepted. 2026-10-07.

**D10 Student login = ID + one-time access code.** Why: ID alone allows impersonation, which breaks fairness. Pending Mayank's approval. 2026-10-07.

**D11 Two parallel Claude Code streams (CORE, VOICE).** Why: one worker cannot fit the plan in 10 days. Cost: double review load. Proposed. 2026-10-07.
