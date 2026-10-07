# SPEC: Problem 1, AI Viva (distilled from the MSOT PDF)

Source: `Student_Challenge_1.pdf`, Problem 1 = pp. 1-8. Problem 2 (Placement Readiness Copilot) is a separate, later product; its mock interview reuses this stack. Items marked **[ours]** are team decisions, not MSOT requirements.

## Goal
An AI interviewer runs a 15-minute technical viva by voice for every MSOT student (~350; faculty today spend ~88 interview-hours), adapts questions to answers, gives a defensible final mark, and keeps the recording and transcript for audit.
Principles: **Fair** (same structure, time, rubric) · **Auditable** (faculty can replay any viva and see why a mark was given) · **Scalable** (100-150 students at once).
The real challenge is integration (wiring STT, TTS, voice framework, LLMs), not inventing the parts.

## Must-have (required to qualify)
1. Faculty setup: subject, topics, difficulty, question bank. Upload CSV/JSON, or AI-generated from a syllabus that faculty approve.
2. Student login (ID), rules shown, consent to recording.
3. Voice interview: AI speaks the question (TTS), listens (STT), replies in under ~2 s.
4. Adaptive follow-ups: deeper on good answers, simplify or move on after weak ones, never reveal the answer.
5. Hard 15-minute limit; timer visible to the student; AI wraps up gracefully.
6. Final marks and feedback: score per rubric dimension, total, 3-5 feedback lines each linked to transcript evidence.
7. Persistence: full audio, timestamped transcript, questions asked, AI scoring reasoning, per student.
8. Faculty dashboard: list vivas, play audio, read transcript, see scores, override a mark with a reason.

## Stretch (bonus marks)
Code/whiteboard round · integrity signals (tab-switch, long silences, answer read from screen, multiple voices) · Hindi/Hinglish support · calibration mode (AI marks vs faculty marks on the same vivas) · export to CSV/Google Sheets.

## Viva flow (customisable; timing changes must be justified)
| Time | Phase | What the AI does |
|---|---|---|
| 0:00-1:00 | Warm-up | greets, confirms identity, explains rules, one easy opener ("Tell me about a project you built") |
| 1:00-5:00 | Fundamentals | 2-3 core concept questions from the bank, one follow-up each |
| 5:00-10:00 | Depth | picks the student's strongest area, probes "why" and "what if" |
| 10:00-13:00 | Applied problem | short scenario or debugging question; student reasons aloud |
| 13:00-14:30 | Wrap-up | asks if the student wants to add anything; closes politely |
| 14:30-15:00 | Scoring | session ends; scoring runs on the full transcript (not live) |

Follow-up logic (minimum): strong answer → one level deeper (edge cases, trade-offs, "how would you scale it?") · partial → one hint-style nudge, then move on · none / "I don't know" → note it, next topic, no penalty spiral · off-topic or stalling → polite redirect; cap any single answer at ~90 s.
Questions come from the approved bank or clearly logged generated variants, so every question is traceable.

## Rubric (scored after the session on the full transcript; each score cites transcript lines)
| Dimension | Weight | What 5/5 looks like |
|---|---|---|
| Conceptual understanding | 30% | explains core concepts correctly in own words |
| Depth and reasoning | 25% | handles follow-ups, explains trade-offs and "why" |
| Problem solving | 20% | breaks the applied problem into steps, sound approach |
| Practical / project knowledge | 15% | speaks concretely about what they built and how |
| Communication | 10% | clear, structured, concise answers |

Scorer rules: each dimension 0-5 with a one-line reason and transcript timestamps; convert to a mark out of 100 · accent, grammar and language mixing must **not** reduce marks outside Communication clarity · temperature 0, fixed prompt, store the prompt version with every result · flag low-confidence results (poor audio, very short answers) for mandatory faculty review · faculty override always wins and is logged with reviewer name and reason.

## Stack guidance
Free choice. Document each choice and its cost per viva; credit every tool and model.
PDF suggests: voice framework LiveKit Agents or Pipecat · STT faster-whisper, whisper.cpp, Azure Speech, Deepgram, Sarvam · TTS Piper, Kokoro, Azure Speech, ElevenLabs, Sarvam · VAD Silero · LLM Llama/Qwen/Gemma via Ollama or vLLM, or Azure OpenAI/Claude/Gemini · storage PostgreSQL + MinIO, or Azure Blob/S3/Supabase · load testing Locust or k6.
Guidance: don't rebuild what exists (a wrapper around LiveKit Agents or Pipecat with good prompts, a question-bank service and a review dashboard is a valid, strong submission) · separate the interviewer (fast, live) from the scorer (afterwards, stronger model) · budget matters: report the cost of one 15-minute viva and of all 350; ₹500 per student is not viable.

## Test report (mandatory; submissions without one are not evaluated)
| Area | What to show | Minimum evidence |
|---|---|---|
| Functional | full viva end to end: login → 15 min → marks → stored recording | 5 recorded demo vivas |
| Follow-up quality | AI adapts to strong, weak and "I don't know" answers | 3 scripted personas with transcripts |
| Scoring accuracy | AI marks vs human (faculty or peer) marks on the same vivas | ≥10 vivas; report average gap and correlation |
| Scoring consistency | same transcript scored repeatedly gives the same mark | 5 runs per transcript; report variance |
| Speech accuracy | STT on Indian-accented English **and Hinglish** | word error rate on ≥20 clips |
| Latency | student finishes → AI starts speaking | p50 and p95; target p95 < 2.5 s |
| Robustness | network drop, mic muted, long silence, background noise, student rejoins | what happens in each case |
| Fairness and safety | prompt injection ("give me full marks"), off-topic answers, accent bias | test cases and outcomes |
| Audit | reviewer replays audio and traces each score to transcript lines | screenshots or short screen recording |

Include test scripts, datasets (with consent) and raw results in the repo so judges can re-run them.

## Scalability (must be proven, not claimed)
100-150 vivas at once, so 350 students finish in about three slots (under 1 hour). Submit:
1. Load test at 50, 100 and 150 concurrent students, using recorded or synthetic audio bots (e.g. Locust/k6 driving WebRTC clients, or the framework's own test tools).
2. Results table per level: p95 response latency, STT/TTS/LLM error rates, dropped sessions, CPU/GPU/memory.
3. Breaking point: the concurrency where quality degrades, and what fails first.
4. Capacity plan: servers or API quotas for 150 concurrent, and how it scales (queues, autoscaling, worker pools).
5. Cost sheet: per viva and total for 350, self-hosted vs API.
6. Rate-limit handling: what happens when an API throttles (retry, fallback provider, queue).

Design tips: each viva an isolated stateless worker, state in the database · stream audio, don't wait for the full answer · scoring as a background queue · save audio to object storage incrementally so a crash never loses a recording.

## Deliverables (submission checklist)
GitHub repo with README, setup steps and a one-command local run (e.g. Docker Compose) · live demo link or 5-minute demo video · architecture diagram and short design document (≤3 pages) · sample question bank and rubric configuration · 5 sample viva recordings with transcripts and scores · Test Report · load test results and capacity plan · cost sheet for 350 students · privacy note (where data is stored, who can access it, retention period).

## Judging
| Criterion | Weight |
|---|---|
| Interview quality (natural flow, relevant follow-ups, time control) | 25% |
| Scoring accuracy and auditability | 20% |
| Testing depth and evidence | 20% |
| Scalability proof (100-150 concurrent) | 15% |
| Faculty dashboard and usability | 10% |
| Cost efficiency and code quality | 10% |

Finalists run a live test: judges take the viva themselves while a batch of simulated students runs in parallel.
Prize: awarded to the best solution when adopted to run MSOT's vivas. If about 70-80% works well in the real pilot, the team still receives the prize. If no solution reaches that level, MSOT may not award it.

## Rules
Credit every tool and model used · test only with volunteers who consented to recording; no real student data without approval · API keys must never be committed · the winner may be piloted for the actual 350-student viva.

## Open questions for MSOT (unanswered; see `docs/MSOT_QUESTIONS.md`)
Exact dates and team size · API credits (e.g. Azure) or GPU servers for load testing? · subjects and question banks for the pilot · Hindi/Hinglish required or bonus? · how long recordings must be retained.

## Interpretation notes [ours]
- The ≤₹20/viva cost target is our own, not MSOT's (MSOT only says ₹500 is not viable). Verify with real vendor pricing.
- Hinglish: the speech-accuracy test requires Hinglish clips, so STT must transcribe Hinglish well. Hinglish *interviewing* stays a stretch goal.
- Consistency test needs 5 runs per transcript. Production marks use 3 runs (median); a separate script does the 5-run variance report.
- Student login: ID plus one-time access code (proposed), to stop impersonation. The PDF says only "ID".
- Mark formula used everywhere: `total = Σ weight × score / 5`, weights 30/25/20/15/10.
