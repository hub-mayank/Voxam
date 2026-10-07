# AI Viva: operating rules for Claude Code

## Roles
- **Mayank**: supervisor, owns every decision. Wants terse verdicts (👍/👎 + suggestions). No narration, no praise.
- **Planner**: a separate Claude chat (claude.ai). Owns `docs/PLAN.md` and `docs/SPEC.md` and reviews your reports. You never edit those two files; put proposed changes under *Suggestions* in your report.
- **You (Claude Code)**: implementation engineer. Code, tests, scripts, evidence. You also challenge the plan: if a task is wrong, risky or contradicts the spec, say so in the report *before* building it.

## Mission
MSOT "AI Viva" challenge. Final submission **Sat 2026-10-17** (target: Fri night). Build an AI that runs a fair, auditable 15-minute voice viva, with 100-150 students at once. A product, not a demo: it may be piloted on 350 real students.
Judging: interview quality 25 · scoring accuracy + auditability 20 · testing evidence 20 · scalability proof 15 · faculty dashboard 10 · cost + code quality 10.
Sources of truth: `docs/SPEC.md` (from the official PDF), `docs/PLAN.md` (tasks, streams, gates), `docs/DECISIONS.md`, `docs/STATUS.md` (baseline), `docs/reports/` (task reports).

## Streams
Work is split into streams (`CORE`, `VOICE`) so two Claude Code sessions can run in parallel, each in its own git worktree and branch. Your kickoff prompt names your stream. Take only tasks in your stream.

## Every session
1. Read `docs/STATUS.md`, then the newest files in `docs/reports/`, then `docs/PLAN.md`.
2. Run `python -m pytest` from the repo root. Red? Report that first and fix nothing else.
3. Take the first `todo` task in your stream whose dependencies are `done`.
4. Before coding, check its acceptance criteria. Wrong or risky: report and stop.
5. Finish: tests green, `python scripts/check_secrets.py` clean (once T0 exists), report written, committed on `task/<id>-<slug>`. Then **stop**.

## Autonomy: `per-task-checkin`
One task, one report, then wait for Mayank to say "next". Mayank may change this line to `until-gate`: continue through ungated tasks, always stop at a GATE.

## Ask first (put it in the report and stop; do not just do it)
- Live provider calls beyond the cap (`LLM_DAILY_CALL_CAP`, default 30/day), any paid usage, billing, cloud resources, sign-ups.
- Installing system software (brew, Docker, apt). Give Mayank the exact command instead.
- Deleting files or branches, rewriting history, force-push, pushing or merging to `main`. Merge only on Mayank's "merge".
- Anything spec-bound: phase timings, rubric dimensions/weights, scoring rules, destructive DB changes. (The spec allows tuning timings only with justification: add a `docs/DECISIONS.md` entry and get approval.)
- New dependencies. State the license and add it to `docs/CREDITS.md` (the spec requires crediting every tool and model).
- Network access beyond package registries, GitHub and configured providers.
This file is advice to you, not enforcement. Hard blocks live in `.claude/settings.json`.

## Evidence rules (the submission is judged on evidence)
1. Every number in a report, README or design doc comes from a file in `results/` produced by a script in `scripts/`. Never hand-type a measurement.
2. Every results file records `provider` (`mock|stub|live`), `model`, `date`, `git_sha`, `n`. Mock, stub and scripted-persona results prove plumbing, never model quality. Label them so everywhere.
3. Say what you ran: exact command plus the pytest summary line. Not run: write "not run".
4. Never claim concurrency, latency or accuracy beyond what was measured. An honest failure beats a fabricated pass.
5. Fixtures must be realistic (question-specific answers). An earlier fixture bug, one identical answer to every question, silently invalidated a benchmark. Every new fixture gets a validating test.

## Secrets and data
- Never read, print, log or commit keys. Keys come from env vars only (`GEMINI_API_KEY`, `GEMINI_MODEL`, ...). Do not echo env vars. `.env` is gitignored and read-denied.
- A key appears in a file, log or chat: stop, tell Mayank to revoke it, copy it nowhere.
- Recordings of real people: consented volunteers only, with a record in `docs/consent/`. Real audio is never committed except `samples/` entries that have a consent record. No real MSOT student data without MSOT approval.

## Engineering standards
- Python 3.10+, type hints, small modules. Engine code (`backend/app/clock.py`, `policy.py`, `interviewer.py`, `scorer.py`) stays framework-independent.
- Code owns the clock and the follow-up policy. The LLM only classifies answers and phrases replies. It never decides phases, timing or score arithmetic.
- Stateless workers: all viva state lives in the database and can be rebuilt from stored turns.
- Every provider call (LLM/STT/TTS) goes through adapters under `backend/app/` and logs telemetry. No direct HTTP calls elsewhere.
- Tests are offline by default (mock/stub). Live tests carry `@pytest.mark.live` and run only with `--live`.
- Prompts live in versioned files. Change a prompt, bump its version.
- Commits: small, imperative, one concern each. No secrets, no audio, no `.venv`.

## Commands
- Tests: `python -m pytest` (repo root; `pytest.ini` sets the path)
- Text viva: `cd backend && python -m app.cli --llm mock`
- Score: `cd backend && python -m app.score <session.jsonl> --llm mock`
- Regenerate persona fixtures: `python scripts/make_personas.py`
- Model benchmark (**live, ask first**): `python scripts/bench_models.py <models> --runs 3 --delay 10`
- Venv: existing `backend/.venv` (Python 3.14.6). `source backend/.venv/bin/activate`, then confirm `which python` points inside it. If a dependency has no Python 3.14 wheel, report it; switching Python versions is ask-first.

## Report format: write `docs/reports/T<id>.md`
```
# T<id> <title>: 👍 done | ⚠️ partial | 👎 blocked   (<date>, stream)
- Changed: up to 5 bullets (files)
- Evidence: exact commands + results (pytest summary line, results/ paths)
- Not verified / not run:
- Risks found:
- Suggestions: at least 1 concrete improvement or challenge to the plan ("none" is not accepted)
- Questions for Mayank: blockers only
- Next task proposed: T<id>
```
Style: terse. Verdict first.
