# Voxam glossary: every term used in the plan, in one line plus the reason (2026-10-13)

How to read: **Means** is the one-line definition. **Why here** is the reason it exists in this project. IDs are the ones in `docs/PLAN.md`, `docs/DECISIONS.md` and `docs/TEAM_PLAN.md`.

## 1. The project and the people
| Term | Means | Why here |
|---|---|---|
| **Voxam** | Product name of our AI viva system. | Chosen 2026-10-08 for the README, UI and demo; repo and packages keep the name `ai-viva` until after submission. |
| **MSOT** | The organisation running the challenge (Problem 1, "AI Viva"). | They set the spec, judge the entries and may pilot the winner on a real 350-student viva. |
| **Viva** | A ~15-minute spoken technical interview. | The thing we automate: fair, same structure for every student, auditable. |
| **Prototype** | The first end-to-end working version (voice viva, scoring, dashboard). | Mayank's priority: get it working first; cost, scale and evidence work come after. |
| **CORE / VOICE** | The two Claude Code work streams (backend/scoring vs voice). | The plan needed ~11.5 days of work in 10 days, so two sessions run in parallel on separate branches. |
| **Planner** | A separate Claude chat that owns `PLAN.md` and `SPEC.md`. | Keeps planning apart from implementation; Claude Code only proposes changes to those two files. |
| **Friend A / B / C** | Teammate slots in the plan: A = Parth (dashboard), B = Tejas (evidence), C = Bhavesh (student pages + voice client). | The plan named roles before the team was confirmed; this maps them to people. |

## 2. Human blockers (things only Mayank or the team can clear)
| ID | Means | Why here |
|---|---|---|
| **B1** | Revoke the Gemini key that was pasted in chat; new keys only in terminal env vars. | A leaked key can be abused and billed; no live calls until it is rotated. |
| **B2** | Zero-spend rule: free tiers and local models only; Mayank collects free keys (Gemini, Groq) and reports Mac specs. | No budget, so evidence must come from free quotas and local models. |
| **B3** | Install PostgreSQL via Homebrew now, Docker Desktop later. | The scoring queue and concurrency claims must be proven on the real target database, not SQLite. |
| **B4** | Invite the three teammates as GitHub collaborators (repo is private). | Nobody can open a PR or read the repo until they have access. |
| **B5** | MSOT's answers (local-first, Hindi/Hinglish required, retention ~1 month, pilot subjects DSA + Web Development) and the still-open questions (cutoff time, finals, iMac specs). | Their answers change the architecture (D22), the language scope and the privacy note. |
| **B6** | ≥ 15 consenting volunteers (10 to be human-marked, 5 for demos) with signed consent in `docs/consent/`. | The rules allow testing only on consenting volunteers; all accuracy and demo evidence depends on them. |
| **B7** | A human marker (peer or faculty) scores ≥ 10 vivas using `docs/marking_sheet.csv`. | Scoring accuracy (20% of the judging) can only be shown by comparing AI marks to human marks. |
| **B8** | Hosting for the finalists' live test. | Judges take a viva themselves while simulated students run; that needs a reachable server. |

## 3. Gates (checkpoints that must pass)
| ID | Means | Why here |
|---|---|---|
| **G0** | API contract frozen (done). | Lets the frontend build against `openapi.json` while the backend is still being built. |
| **G1** | Voice stack chosen from measured latency (done: no Plan B). | Latency is the biggest technical risk, so it was measured before building around it. |
| **G2** | One real human completes a voice viva and the recording replays. | Proves the whole voice path works for a person, not just scripts. Was due 10-12; now Thu 10-15 (M3). |
| **G3** | Feature freeze: only fixes, evidence and docs after this. | Protects the last days for the mandatory Test Report. |
| **G4** | Code freeze (Fri 18:00): a clean clone runs a full viva with one command. | Judges re-run the repo; it must work from scratch. |
| **M1 / M2 / M3** | Prototype milestones: text-mode end to end (Wed 12:00), push-to-talk voice (Wed 22:00), hands-free voice + replay + Mayank's viva (Thu 12:00). | Small, checkable steps so a slip is visible a day early. |
| **Plan B** | Half-duplex fallback: student presses to speak and to submit. | Triggers if end-to-end latency p95 exceeds 4 s; measured p95 is about 2 s on the chosen stack, so it is not needed. |

## 4. Tasks (status as of 2026-10-13)
| ID | Means | Why here |
|---|---|---|
| **Q0** (done) | Repo hygiene: rewrote `CLAUDE.md`, removed stale and invalid results. | Judges grade evidence; stale or invalid files would undermine it. |
| **T0** (done) | Guardrails: secrets scan, call cap, live-test flag, credits file. | Prevents leaked keys, accidental spend and fake "live" results. |
| **T1** (done) | Telemetry and provider resilience (retries, fallback chain, Ollama adapter). | Every number in the report must come from logged calls; providers fail and must not stop a viva. |
| **T1c** (done) | Free-first providers (Groq etc.), per-model free-tier budgets, Postgres job-claim proof. | Zero-spend rule made enforceable in code; proves two workers never take the same job. |
| **T1b** (todo, needs Mayank's go) | Live baseline: run the personas through a real model, 4 personas × 3 runs. | The repo holds no real-model results; also measures real tokens per call, which every cost figure needs. |
| **T2a** (done) | API contract: routes, schemas, mock server, `openapi.json`. | Unblocks the frontend before the backend exists. |
| **T2b** (done) | Stateless engine and persistence: rebuild a viva from stored turns, server clock, rejoin. | A crash or restart must never lose or corrupt a viva. |
| **T3 / T3b** (done) | Voice spike: measured STT/LLM/TTS stacks, WER, latency; closed the missing legs with real models. | Picked the voice stack with numbers and showed Plan B is not needed. |
| **T4** (todo, VOICE) | Voice integration: WebSocket, VAD, STT, engine, TTS, audio saved, timer, hard stop. | The core of the product; also the schedule's critical path. |
| **T5** (done) | Scoring worker: queue, retries, 3 runs → median, evidence, low-confidence flags, consistency script. | Auditable scores: every mark has a reason and cites transcript turns. |
| **T6** (todo, Parth + Bhavesh) | Dashboard and student pages. | Faculty must review, override and replay; students need a usable way to take the viva. |
| **T7** (todo, VOICE) | Load harness: 10–150 simulated sessions, stub vs live labelled. | Scalability proof is 15% of the judging; stubs prove our system, small live runs prove the vendors. |
| **T8** (todo) | Evidence runs: follow-up quality, scoring accuracy vs humans, WER on ≥ 20 clips, robustness, fairness probes. | The Test Report is mandatory; submissions without one are not evaluated. |
| **T9** (todo, CORE) | Cost and capacity: ₹ per viva and per 350, from telemetry × priced rows. | Cost efficiency is judged; every cost claim needs a source. |
| **T10** (todo) | Docs and submission: README, architecture diagram, design doc, privacy note, report generator, samples. | The submission checklist; judges re-run it. |
| **T11** (todo) | Hosting for the finals. | Needed for the live test (B8). |
| **P0** | The team-plan branch (`task/P0-team-plan`). | Holds this glossary and `TEAM_PLAN.md`. |
| **PA / BH / TJ / CL** | Card IDs: Parth, Bhavesh, Tejas, Claude (in `TEAM_PLAN.md`). | Each card is one small PR with a "Done when" line. |
| **V1 / V2 / V3** | Voice sub-milestones: scripted bot, browser push-to-talk, hands-free. | T4 is split so something works early. |

## 5. Decisions (`docs/DECISIONS.md`)
| ID | Means | Why here |
|---|---|---|
| **D1** | Code owns the clock and follow-up policy; the LLM only classifies and phrases. | Same structure for every student (fairness) and testable. |
| **D2** | Interviewer and scorer are separate; scoring runs after the session, 3 runs → median. | The spec requires it; keeps the live path fast. |
| **D3** | All providers sit behind adapters with telemetry; mock by default. | Evidence comes from telemetry; no accidental live calls. |
| **D4** | Provisional model `gemini-3.5-flash`. | Placeholder until a benchmark; superseded in practice by the free-tier chain. |
| **D5 / D12** | SQLite for dev, PostgreSQL target, DB-backed scoring queue, no Redis. | Fewer moving parts; the job is created in the same transaction that ends the session. |
| **D6** | Scale proof in two layers: stubs at 50–150, live at ≤ 20. | A free tier cannot serve 150 live; every result row says stub or live. |
| **D7** | Voice stack undecided (now settled by D19). | Kept the choice open until measured. |
| **D8** | Cost target ≤ ₹20 per viva is ours, not MSOT's. | An internal yardstick to design against. |
| **D9** | STT must handle Hinglish; Hinglish interviewing stays stretch. | Indian students mix languages; MSOT later made Hindi/Hinglish required. |
| **D10** | Student login = ID + one-time access code. | ID alone allows impersonation. |
| **D11** | Two parallel Claude streams (CORE, VOICE). | One worker cannot fit the plan in 10 days. |
| **D13** | The SQLAlchemy models are the schema; `schema.sql` is generated. | One source of truth, drift caught by a test. |
| **D14** | API conventions frozen: ms durations, UTC `Z` timestamps, signed audio URL, bank locked after first join. | Friend A builds against stable rules. |
| **D15** | Zero-spend policy: free tiers, local models, never pay-as-you-go. | No budget; protects Mayank from accidental billing. |
| **D16** | Engine runtime: one answer at a time per session, state rebuilt from turns, growing delay for wrong codes, lazy session end. | Restart-safe and hard to abuse. |
| **D17** | PostgreSQL via Homebrew; psycopg v3 driver. | Concurrency claims need the real target database. |
| **D18** | Free-tier budget registry: per-model rolling daily limits and per-minute pacing. | Stops us causing 429s and exceeding quotas. |
| **D19** | Voice stack: custom WebSocket, Silero VAD, whisper.cpp, Groq gpt-oss-20b live (Ollama fallback), Piper alba. | Measured on real models; records the Groq daily-token limit as the open risk. |
| **D20** | Budget also enforces tokens per minute and per day. | Groq's token limit binds before its request limit. |
| **D21** | Scoring worker design: lease, retries, atomic rescore, flags. | Makes scoring crash-safe and auditable. |
| **D22** (pending) | Local-first architecture: local profile now, sync bundle later. | MSOT asked for client-side processing; not yet recorded. |

## 6. Technical terms
| Term | Means | Why here |
|---|---|---|
| **STT / TTS** | Speech-to-text / text-to-speech. | The two ends of the voice pipeline. |
| **VAD** | Voice activity detection: finds where speech starts and ends. | Decides when the student has finished answering. |
| **LLM** | The language model. | Classifies answers, phrases follow-ups, writes scores. |
| **classify / phrase** | The interviewer's two LLM calls per answer: rate the answer, then word the reply. | Code decides what happens; the model only labels and words it. |
| **E2E latency (p50, p95)** | Time from student stops speaking to first AI audio; median and 95th-percentile. | p95 under 2.5 s is the goal; above 4 s triggers Plan B. |
| **WER** | Word error rate of a transcript against a reference. | Judges require it on ≥ 20 Indian-accented and Hinglish clips. |
| **Hinglish** | Hindi-English mixed speech. | Required by MSOT; must not lower non-Communication marks. |
| **whisper.cpp / Piper / Ollama / Groq / Gemini / Azure Speech** | Local STT / local TTS / local LLM server / fast free cloud LLM+STT / Google LLM / Microsoft voice service. | The concrete providers behind D19; each sits behind an adapter. |
| **Adapter** | One module per provider with the same interface and telemetry. | Swapping provider or tier is a config change. |
| **Fallback chain** | Ordered list of providers tried in turn. | A rate-limited or down provider must not stop a viva. |
| **Telemetry** | JSONL log of every provider call (latency, tokens, status). | Source of every latency and cost figure. |
| **Budget / rpm, rpd, tpm, tpd** | Free-tier limits: requests or tokens per minute/day. | We refuse calls before the provider rate-limits us. |
| **Job queue / lease / idempotent** | DB table of scoring jobs / a time-limited claim / safe to repeat. | Several workers can run; a dead worker's job is taken over; no double scoring. |
| **Rubric** | The 5 scored dimensions and weights (conceptual 30, depth 25, problem 20, practical 15, communication 10). | Spec-bound; total = Σ weight × score / 5. |
| **Evidence turn** | Transcript turn a score cites. | Makes every mark auditable and replayable at the audio offset. |
| **Low-confidence flag / needs review** | Result marked for a human look (short answers, repeated "I don't know", shaky STT, missing audio...). | Faculty see where the AI is least reliable. |
| **Override / review / rescore** | Faculty change a mark with a reason / mark it checked / queue scoring again. | The AI proposes; a human decides, with a logged trail. |
| **ai-draft / bank / approve** | Question source labels / reviewed questions / action that promotes a draft. | AI-written questions need faculty sign-off before real use. |
| **Access code** | One-time code per student. | Part of D10. |
| **Persona / injection** | Scripted student (strong, weak, idk, injection) / answer that tells the scorer to give full marks. | Test inputs for scoring and fairness. |
| **Stub / mock / live** | Simulated provider / deterministic fake / real provider. | Results are always labelled; mock and stub prove plumbing, not quality. |
| **Local / central profile** | Run everything on the viva machine / central server that scores and shows the dashboard. | The shape of D22. |
| **Sync bundle** | Export of a finished local session sent to the central server. | Moves results without moving the whole system. |
| **Router** | Sends classify, phrase and score to different models. | Cheapest model for the high-volume call; better ones where they matter. |
| **TTS cache** | Pre-rendered audio for fixed lines (bank questions, opener, closer). | Zero marginal cost and latency for most turns. |

## 7. Evidence and process
| Term | Means | Why here |
|---|---|---|
| **Test Report** | Document built from `results/` showing every claim's source. | Mandatory: without it the submission is not evaluated. |
| **Results sidecar (`.meta.json`)** | File next to each result with provider, model, date, git sha, n. | Proves what produced a number and whether it is mock, stub or live. |
| **Ask-first** | Actions Claude must get approval for (live calls over the cap, new dependencies, merges...). | Protects budget, licences and `main`. |
| **Consent register** | List of volunteer IDs with consent date and public-demo yes/no. | Shows every recording has consent without storing names in git. |
| **Marking sheet** | CSV where a human marker scores a viva on the same rubric. | The ground truth for scoring accuracy. |
| **CREDITS** | `docs/CREDITS.md`: every tool, model and licence. | The spec requires crediting everything used. |
