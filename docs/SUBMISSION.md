# Voxam: submission map

One page for judges: what each judging criterion asks, what we built, which file proves it, and what is **not** proven. Numbers are not
retyped here; each one lives in the file named next to it (`results/`, with a `.meta.json` sidecar saying provider, model, date, commit and n).
Rows marked **TO FILL** wait for the volunteer vivas and marker sheets (`docs/qa/VOLUNTEER_VIVAS.md`) and are updated from the generated report, not by hand.

Status words: **done** (built and evidenced), **partial** (built, evidence limited as stated), **missing** (not shown yet).

## How to see it (5 minutes)
- Local, one command: `scripts/run_local.sh`, then `cd frontend && npm run dev` (README, "Local profile"). No hosting is used (decision D26); for the finals `scripts/run_finals.sh` serves one address, with an optional free tunnel (`docs/FINALS_RUNBOOK.md`).
- Script for the demo: `docs/DEMO_SCRIPT.md`. A populated dashboard without running a viva: `scripts/seed_demo.py` (fake data, labelled DEMO).
- Tests: `python -m pytest -q` (repo root) and `cd frontend && npm run check`. Secret scan: `python scripts/check_secrets.py`.

## Criteria
### Interview quality (25)
| Built | Evidence | Status and limits |
|---|---|---|
| Hard 15-minute clock owned by code; phases warm-up, fundamentals, depth, applied, wrap-up; the LLM only classifies and phrases (D1, `backend/app/clock.py`, `policy.py`, `interviewer.py`). | `docs/SPEC.md`, `docs/DECISIONS.md` D1, `backend/tests/test_restore.py` (state rebuilt from stored turns). | done |
| Follow-ups adapt to strong, weak and "I don't know" answers; no model call for a clear "no answer". | `results/followup_groq_gpt-oss-20b.csv`, `results/followup_groq_gpt-oss-20b_weak.csv`, `results/followup_ollama_llama3.2_3b.csv` (scripted personas, live models). | partial: scripted personas, not real students; the local 3B model's follow-ups are weaker than the cloud model's. |
| Hindi and Hinglish answers accepted; the AI replies in English. | prompts `interviewer-v3`; `results/consistency_groq_gpt-oss-20b_hinglish_v3_summary.csv`. | partial: speech recognition on Hinglish is weak (`results/voice_spike/`, real clips); the language is chosen on the Ready screen. |
| One cross-check question per viva, taken from the student's own opener (D27). | `backend/tests/test_restore.py`, `docs/INTEGRITY.md`, `docs/qa/integrity-cross-check-log.md`. | partial: quality on real vivas is **TO FILL** (cross-check log). |

### Scoring accuracy and auditability (20)
| Built | Evidence | Status and limits |
|---|---|---|
| Rubric of five weighted dimensions, three scoring runs with the median, structure validation, low-confidence flags, human override with a reason, rescore. | `config/viva.config.json`, `docs/reports/T5.md`, `backend/tests/test_scoring_worker.py`, `backend/tests/test_real_faculty.py`. | done |
| Same transcript scored repeatedly. | `results/consistency_groq_gpt-oss-20b_v3_summary.csv` | partial: scripted transcripts; a single AI mark is noisy (the weak persona's mark moved a lot between runs, `docs/reports/SV5.md`). |
| Every mark traces to transcript turns and the recording; the faculty page shows reasons, evidence links, audio seek and overrides. | `docs/API.md` (session detail), `frontend/src/faculty/`. | done; replay screenshots **TO FILL**. |
| **AI marks against human marks, at least 10 vivas, two markers.** | `scripts/marking_packet.py`, `scripts/compare_markers.py`, `docs/qa/MARKER_GUIDE.md`, output `results/accuracy_vs_human.csv`. | **TO FILL**. Not shown until the marker sheets are back. Team members role-play the students; this is stated in the report. |
| Failed marking is explained, not hidden. | `scoring_error` on failed sessions (`docs/CHANGELOG-api.md`), `docs/reports/SE1.md`. | done |

### Testing evidence (20)
| Built | Evidence | Status and limits |
|---|---|---|
| Automated suite, offline by default; live tests are marked and opt-in. | `python -m pytest -q`; frontend `npm run check`. | done |
| Fairness and safety: prompt injection, off-topic answers, accent and language mixing. | `results/fairness_groq_gpt-oss-20b.csv`, `results/fairness_groq_gpt-oss-20b_mixing_v3_n3.csv`, `results/fairness_groq_gpt-oss-20b_mixing_v3_fillerstrip_n3.csv`, `docs/reports/T8.md`, `FP1.md`, `SV5.md`. | partial: injection hardened; **broken English still loses some marks on the scripted probe** (see the reports); real non-fluent speech is **TO FILL**. |
| Robustness: network drop, muted mic, long silence, rejoin. | `results/robustness_scenarios.csv`. | done for the listed cases. |
| Latency, speech accuracy. | `results/voice_e2e_local_groq.csv`, `results/voice_spike/wer_real_clips.csv`. | partial: latency was above the 2.5 s target at p95 when last measured; speech accuracy rests on very few real clips (the spec asks for 20). Re-measurement **TO FILL**. |
| Generated test report. | `python scripts/build_report.py` | the "gaps" table in it lists what is still missing. |

### Scalability proof (15)
| Built | Evidence | Status and limits |
|---|---|---|
| Stateless workers, database job queue, capacity settings, a load harness with modelled providers. | `docs/reports/T7.md`, `T7b.md`, `T9.md`, `results/load/*.csv`, `docs/DESIGN.md`. | partial. **STT, TTS and the LLM are models of measured behaviour (`provider=stub`)**, harness and server share one machine. One machine saturates at about the level named in `T7.md`. |
| Real Piper throughput by process count. | `results/load/piper_procs.csv` (`provider=live`). | done for TTS alone. |
| Real-model load run. | not run | **missing** unless the Saturday run is done. We do not claim 100-150 simultaneous real vivas. |

### Faculty dashboard (10)
Create a viva, upload a question bank (JSON/CSV) and a roster, issue and revoke access codes, filter sessions, open a viva (transcript, audio, scores with evidence, integrity signals, override with reason, review note, rescore), export CSV, release results to students. See `frontend/src/faculty/README.md`. **done**; layout polish is partial (single long column on the session page).

### Cost and code quality (10)
Free tiers and local models only (D15); cost per viva from priced rows (`results/cost_model.csv`, D25, `docs/pricing.csv`); credits for every tool and model (`docs/CREDITS.md`); decisions logged (`docs/DECISIONS.md`); API contract frozen and tested (`docs/openapi.json`, `docs/CHANGELOG-api.md`); small modules, tests with every change, reports for every task (`docs/reports/`). **done**

## Integrity (bonus)
Tab, focus, paste and copy signals are shown to faculty and never change a mark; one cross-check question; the student is told in the rules text. **A web page cannot stop tools such as Cluely and we do not claim to.** Details and limits: `docs/INTEGRITY.md`.

## What we did not build, and what we do not claim
- No webcam or screen proctoring, no blocking of other apps, no automatic penalty from any signal.
- No hosted service: local-first, as MSOT asked (`docs/MSOT_QUESTIONS.md`, D26).
- No claim about accuracy against humans until `results/accuracy_vs_human.csv` exists.
- No claim of real-model concurrency beyond what `results/` shows.
- Hinglish speech recognition is the weakest part of the voice path.

## Privacy and consent
`docs/PRIVACY.md` (what is stored, retention about one month, how to purge: `scripts/purge_expired_sessions.py`). Recordings only of consented volunteers (`docs/consent/`); none are committed.
