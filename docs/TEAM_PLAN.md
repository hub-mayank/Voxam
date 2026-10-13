# Voxam prototype: team plan (written 2026-10-13, IST)

**Goal (prototype):** by **Thu 10-15 12:00** a student takes a ~15-minute *voice* viva in the browser on the **local profile** (no cloud keys), it is stored and scored (3 runs), and faculty see transcript, audio, scores, reasons and evidence in the dashboard.
**After the prototype** (not now): model router and cost-per-viva meter, sync bundle for local-first, live baseline (T1b), load test, evidence runs, report. Evidence *preparation* (consent, volunteers, clips, question bank) starts today because the Test Report is mandatory and needs ~1.5 days.

## 1. Context pack (read in this order, ~15 min)
1. `README.md`: what exists and the run commands.
2. `docs/API.md` + `docs/openapi.json`: the frozen HTTP contract. Mock backend: `CONTRACT_STUB=1` (see API.md). Real backend with demo data: `scripts/seed_demo.py`.
3. `docs/VOICE_PROTOCOL.md`: the WebSocket contract for voice (Claude writes it **today**; Bhavesh builds against it).
4. `docs/DECISIONS.md`: D1 (code owns the clock, LLM only classifies/phrases), D10 (ID + access code login), D14 (API conventions), D19 (voice stack), D21 (scoring worker).
5. `docs/reports/T5.md` and `T3.md`: what is built and measured.

**How it works in six lines:** student joins with ID + one-time code, accepts rules, starts. Each answer goes to the engine, which classifies it and decides the next question by code (clock and policy are ours); the LLM only phrases. Turns are stored with audio offsets. When the session ends, a worker scores it 3 times and stores the median with reasons and evidence turns. Faculty review, override, export. Voice = browser mic → WebSocket → VAD + STT → engine → TTS → browser.

## 2. Rules for everyone
- Branch `feat/<name>-<slug>` from `main`, PR into `main`; **only Mayank merges**. Never push to `main`.
- PR ≤ ~400 changed lines, one concern, with a screenshot or short clip and "how to run it".
- Edit only your own paths (table below). Need something outside them? Say so in the PR; do not edit it.
- No keys, no real student data, no audio in git. Run `python scripts/check_secrets.py` before every PR.
- Backend: `python -m pytest -q` must pass. Frontend: `npm run build` and `npm run lint` must pass.
- AI tools are fine. Add one line per tool to `docs/CREDITS.md`. No `Co-Authored-By` or "generated with" lines in commits.
- Frontend style: React function components, single quotes, no semicolons, 2-space indent, one component per file.
- Blocked more than 30 minutes? Post it in the group chat with the PR link or error. Do not wait silently.

## 3. Who owns what
| Person | Owns | Paths (only these) |
|---|---|---|
| **Parth** (dev-sarthi) | Frontend scaffold, **faculty dashboard** | `frontend/` (all, except `src/student/`) |
| **Bhavesh** (Src-Bhavesh) | **Student pages and browser voice client** | `frontend/src/student/**` |
| **Tejas** (tejaa11) | **Evidence and data**: consent, volunteers, question bank, clips, WER script, clean-machine test | `docs/consent/**`, `config/question_bank.webdev.*`, `backend/tests/test_question_bank_webdev.py`, `evidence/**`, `scripts/wer.py`, `docs/marking_sheet.csv` |
| **Mayank** | Reviews and merges, keys, decisions, MSOT questions, one human viva | n/a |
| **Claude CORE session** | Protocol doc, one-command local run, first-pass review of every PR | `backend/app/**` except voice, `scripts/**`, `docs/openapi.json`, `docs/*.md` |
| **Claude VOICE session** | Voice integration (T4) | `backend/app/voice/**`, `backend/app/api/routes_voice.py`, `backend/tests/test_voice_*` |

## 4. Schedule and milestones
| When | Parth | Bhavesh | Tejas | Claude |
|---|---|---|---|---|
| **Tue 10-13** | PA-1 scaffold PR by 14:00, then PA-2 | BH-1 (text flow), BH-2 starts | TJ-1, TJ-2, TJ-3 start | CL-1 protocol, CL-2 local run, CL-5, V1 starts |
| **Wed 10-14** | PA-3, PA-4 | BH-2, BH-3 | TJ-2 done, TJ-3 done; evening: TJ-4 clean-machine test | V1 done, V2 |
| **Thu 10-15** | PA-5, bugs | BH-3 hands-free, polish | volunteers' vivas (TJ-5) | V3, reviews |
| **Fri 10-16** | bugs | bugs | TJ-6 WER run, marking | evidence, docs, **code freeze 18:00** |

- **M1 Wed 12:00:** text-mode viva end to end in the browser against the real backend; worker scores it; dashboard shows it.
- **M2 Wed 22:00:** push-to-talk voice in the browser, on Mayank's Mac.
- **M3 Thu 12:00:** hands-free voice, hard stop at 15:00, audio replay in the dashboard, Mayank's own viva. **Feature freeze Thu 18:00.**
- Slip rule: if M2 slips past Thu 06:00, we ship push-to-talk only and say so (Plan B in `docs/PLAN.md`).

## 5. Task cards
Each card: **Do** then **Done when**. Cards are small on purpose: one PR each.

### Parth: dashboard
- **PA-1 Scaffold (first, unblocks Bhavesh).** `frontend/`: Vite + React + TypeScript; `npm run gen:api` makes a typed client from `docs/openapi.json` (openapi-typescript); `VITE_API_URL` defaults to `http://localhost:8000`; router with `/faculty/*` and `/student/*`; `frontend/README.md`. **Done when:** `npm run dev` shows a login page and `npm run build` passes. PR by Tue 14:00.
- **PA-2 Login, viva list, session list.** Token login (check with `GET /faculty/vivas`), viva list, session list with status / low-confidence / search filters and cursor pagination. **Done when:** works against the mock backend and the seeded real one.
- **PA-3 Session detail.** Transcript by `idx`; per-dimension score, reason and evidence chips that scroll to the turn; 3 run totals and spread; low-confidence badge with reasons; audio player with click-to-seek using `turn.t_start_ms`. **Done when:** a seeded scored session shows all of it.
- **PA-4 Actions.** Override (reason required, shows history), review note, rescore button, CSV export, release-results toggle. **Done when:** each action updates the screen and survives a refresh.
- **PA-5 Bank and roster.** Upload CSV/JSON with per-row 422 errors; show `ai-draft` badge and the **Approve** action (`POST /faculty/vivas/{id}/questions/approve`); show issued access codes once (copy button). **Done when:** bad upload shows every row error; approval flips the badge.

### Bhavesh: student pages and voice
- **BH-1 Text-mode student flow** (inside `frontend/src/student/`; until PA-1 merges, work in a scratch Vite app and move it over). Join (viva ID, student ID, access code) → rules + consent → start → question screen with typed answers → end screen. Server-driven countdown from `remaining_ms` (re-sync on every response). Handle every error code in `docs/API.md` (wrong code with `retry_after_ms` countdown, `deadline_passed`, `bad_client_seq`). Rejoin works. **Done when:** a full viva completes against the real backend.
- **BH-2 Mic check and audio module.** AudioWorklet capturing 16 kHz mono PCM16 frames, input level meter, permission-denied and no-device messages, playback queue for audio chunks. Test it on a standalone page first. **Done when:** a recorded 10 s clip plays back clean.
- **BH-3 Voice session client** per `docs/VOICE_PROTOCOL.md`. Order: (1) push-to-talk, (2) hands-free (server detects end of speech), (3) reconnect and text fallback when the mic fails. Show live transcript, "AI speaking" state, timer. Develop against `VOICE_PROVIDER=stub` (no models needed; Claude ships it in V1). **Done when:** a 3-minute voice viva completes in Chrome with the stub and with the real stack on Mayank's Mac.

### Tejas: evidence and data
- **TJ-1 Consent and volunteers (start today).** Fill every `<...>` in `docs/consent/consent_form_template.md` (contact, storage location, retention: assume 1 month, per MSOT's answer; providers: whisper.cpp, Piper, Ollama, Groq). Get **≥ 15 signed forms** (10 to be human-marked, 5 for demo). Keep signed forms outside git; add `docs/consent/register.csv` with volunteer ID, date, public-demo yes/no (no names). **Done when:** register has ≥ 15 rows by Wed night.
- **TJ-2 Web Development question bank.** 30 questions in the schema of `config/question_bank.dsa.json` (24 concept, 6 applied, 3–5 key points, difficulty mix like the DSA bank, `source: "ai-draft"`) plus a CSV twin. Copy `backend/tests/test_question_bank_dsa.py` into a webdev version. **Done when:** that test passes and the bank uploads through the API with no warnings.
- **TJ-3 Recording script and clips.** ≥ 20 clips: ≥ 10 technical English answers in Indian accents, ≥ 10 Hinglish. Follow `spikes/voice/RECORDING.md`. Reference transcripts in `evidence/wer/refs.csv` (clip ID, language, text). Audio goes to a shared drive, **not git**. **Done when:** 20 clips + refs, consent IDs noted per clip.
- **TJ-4 Clean-machine test (Wed night, again Fri).** Fresh clone on a machine that has never run it; follow `README.md` only; file every snag as a GitHub issue with the exact error. **Done when:** a list of issues, or "ran clean".
- **TJ-5 Volunteers' vivas (Thu afternoon).** Schedule 10 volunteers on Mayank's machine or any Mac running the local profile; help each do the viva; keep session IDs. Find a human marker (faculty or senior) for `docs/marking_sheet.csv`. **Done when:** 10 sessions exist and each has a marker row by Fri noon.
- **TJ-6 `scripts/wer.py`.** Port `spikes/voice/wer.py` + `bench_wer.py` to a script that reads `evidence/wer/refs.csv` and the clips folder; writes `results/wer_*.csv` with a `.meta.json` sidecar (`backend/app/results_meta.py`). **Done when:** it runs on the 20 clips and has a unit test.

### Claude (two sessions; Mayank runs them)
- **CL-1 `docs/VOICE_PROTOCOL.md`** (today): message types, audio format, push-to-talk and hands-free flows, errors, reconnect. Frozen once Bhavesh starts BH-3; later changes need a changelog line.
- **CL-2 One-command local run** (today): `scripts/run_local.sh` starts API + worker on SQLite, seeds a DEMO viva with the DSA bank approved, prints access codes. **Done when:** a clean clone gets a working viva in one command.
- **CL-5 Fix the red suite** (`test_voice_spike.py` needs `jiwer`).
- **V1 / V2 / V3 (T4):** V1 scripted bot completes a push-to-talk viva over the WebSocket (stub and real STT/TTS, pre-rendered TTS for bank questions); V2 works with Bhavesh's browser client; V3 hands-free VAD, hard stop, rejoin, audio saved, STT confidence stored.
- **CL-4 First-pass review** of every PR within 2 h of opening (correctness, paths, tests, secrets), with a one-line verdict for Mayank.

## 6. Review protocol (keeps Mayank's load at about 1 to 1.5 h/day)
1. Author opens a PR with the template: what, how to run, screenshot/clip, tests run, paths touched.
2. Claude CORE posts a first-pass review comment: ✅ / ❌ and the blocking items.
3. Mayank reviews in **two fixed windows a day** (pick the times; suggestion: 13:00 and 20:00 IST). Checklist, about 10 min each: (a) tests/build stated green, (b) only owned paths touched, (c) demo shown and it matches the card's "Done when", (d) no secrets or audio, (e) CREDITS line if a tool or dependency was added.
4. Merge order: PA-1 first, then everything else. Conflicts in shared files (`frontend/src/api`, `docs/openapi.json`) are resolved by Parth and Claude respectively, not by teammates.
5. Expected volume: about 20 PRs over three days.

## 7. Start prompt (paste into your AI tool, replace the card IDs)
> You are helping on the Voxam repo (`hub-mayank/ai-viva`). Read `docs/TEAM_PLAN.md` sections 1, 2 and the cards `<IDs>`. Work only in my owned paths. Do one card per branch `feat/<name>-<slug>` and one PR per card, ≤ 400 lines. Follow the Done-when line exactly, run the tests/build, then show me what changed and how to run it. Never commit keys or audio. If a card needs something outside my paths, stop and tell me.

## 8. Risks and fallbacks
| Risk | Plan |
|---|---|
| T4 slips | Ship push-to-talk only (M2); hands-free is a bonus. |
| Teammates cannot run whisper.cpp/Piper locally (3 GB of models) | `VOICE_PROVIDER=stub` for frontend work; real stack only on Mayank's Mac. |
| Evidence starts too late | TJ-1, TJ-3 run now, independent of the prototype. |
| Merge conflicts | Path ownership above; `frontend/src/api` only via `npm run gen:api`. |
| Browser mic needs HTTPS | `localhost` works over http; deployed demo needs HTTPS (parked with hosting). |

## 9. Defaults I used (change any of them and tell me)
Local-first = D22 option A (local profile now, sync bundle after the prototype); Hindi/Hinglish: understand it, interview in English; retention assumed 1 month; review windows 13:00 and 20:00 IST; teammates are invited as collaborators (B4) and have the repo; frontend in React + Vite + TypeScript.
