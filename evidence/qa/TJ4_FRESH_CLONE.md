# TJ-4 fresh-clone check — 2026-10-15 (IST)

**Partial, with reproducible setup defects.** This is a fresh GitHub clone and new backend virtual environment on
the existing Mac, not a pristine second computer. The scheduled Friday 2026-10-16 repeat is still pending. No
volunteer data, browser microphone session, real model/voice run or complete browser flow was tested.

Tested main commit: `49b92a7aa9e474bfac09ebaafcb701cb732da3ec`.
See the captured [environment and command statuses](tj4_2026-10-15/environment.json) and
[installed backend packages](tj4_2026-10-15/backend-packages.txt). Core requirements installation and the README's
hook installer succeeded. No optional voice-spike libraries were added to hide the advertised test-suite failure.

## README-only setup findings

| Step | Observed result | Evidence / follow-up |
|---|---|---|
| Create venv, install `backend/requirements.txt`, install hooks | Passed | Environment record and package snapshot above |
| Run `python -m pytest -q` with that venv | Exit 2 during collection: missing `jiwer` from the unconditionally imported voice-spike helper | [pytest output](tj4_2026-10-15/pytest.txt), [issue #33](https://github.com/hub-mayank/ai-viva/issues/33) |
| Run root README's `cd frontend && npm run dev` in a fresh clone | Exit 127: `vite: command not found`; dependency installation is absent from this root README path | [startup output](tj4_2026-10-15/frontend-start.txt), [issue #34](https://github.com/hub-mayank/ai-viva/issues/34) |

Commands used, from the fresh clone (explicit venv Python is equivalent to activating it first):

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python scripts/install_hooks.py
backend/.venv/bin/python -m pytest -q
cd frontend
npm run dev
```

The install used the public PyPI index explicitly; the package snapshot records the versions actually resolved.
No existing backend venv, frontend `node_modules`, model weights or environment file were copied into this clone.
The frontend command was tested independently after the backend collection failure; it is not a claim that the
whole quick start passed. The separate frontend README does include `npm install`; the reported gap is in the root instructions.

## Additional offline local-profile check

To prevent unintended model calls, the local-launcher check explicitly selected the README's mock/stub options:

```bash
LLM_CHAIN=mock SCORER_LLM_CHAIN=mock VOICE_PROVIDER=stub PORT=8019 \
TELEMETRY_FILE=/private/tmp/ai-viva-tj4-local-telemetry.jsonl scripts/run_local.sh
```

The [sanitized smoke record](tj4_2026-10-15/local-profile.json) reports a sandbox denial when binding localhost.
The process exited before readiness, so `/health` and `/docs` were **not reached**. Automatic permission approval
for the escalation timed out before execution; this is an environment limitation, not evidence of a product bug.
All processes started by the confirmed attempt were stopped. The output omits printed access codes and tokens;
private launcher/API logs and the seeded test database are not committed.

## Follow-up required

- The core owner resolves the optional-test dependency policy and the root README frontend install step under the
  linked issues. Tejas's owned evidence paths do not include those source/dependency files.
- Repeat the documented commands with a new venv and no frontend dependencies after the fixes; preserve failure
  output as well as successful checks. Run the Friday repeat and an actual separate clean-machine pass.
- Verify startup and the browser/voice path in an environment that permits localhost listening. Mock/stub HTTP
  success would prove startup/plumbing only; real speech quality and volunteer/marking evidence remain separate tasks.

This PR supplies observed setup evidence and issue links. It does not close TJ-4's full operational checklist.
