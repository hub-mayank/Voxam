# Voxam frontend

React + Vite + TypeScript. Faculty screens in `src/faculty/` (Parth), student screens in `src/student/screens/` (Bhavesh),
everything else is the shared foundation (Claude, CL-4/CL-5): `src/api`, `src/shared`, `src/student/session`, `src/student/voice`.

## Run
```bash
scripts/run_local.sh                  # repo root: backend + worker + seeded LOCAL viva (prints codes, faculty token demo-token-0123456789)
cd frontend && npm install && npm run dev      # http://localhost:5173 (API at http://localhost:8000, change with VITE_API_URL)
```
No backend yet? Mock server with example payloads: `CONTRACT_STUB=1 FACULTY_TOKENS="demo:demo-token-0123456789" CORS_ORIGINS="http://localhost:5173" python -m uvicorn app.api.main:app --port 8000` from `backend/`.

## The check you must pass before a PR
```bash
npm run check     # schema is current + types + lint + tests
python ../scripts/check_paths.py <your-name>      # from frontend/: only your files changed
```

## What the foundation gives you
| You need | Use | File |
|---|---|---|
| A faculty API call | `const { api } = useFacultyApi()` then `api.listSessions(...)` etc. | `src/api/useFacultyApi.tsx`, `src/api/faculty.ts` |
| Student login, answers, timer | `const session = useSession()` (`join`, `accept`, `start`, `submitAnswer`, `remainingMs`, `phase`, `error`) | `src/student/session/` |
| Types of every request and response | `import type { SessionDetail } from '../api/types'` | `src/api/types.ts` (generated names in `schema.ts`) |
| Voice: connect, hold-to-talk, transcript, AI text and audio, timer, errors, typing fallback | `import { useVoiceSession } from '../voice'` | `src/student/voice/` (try it by hand at `/student/voice-lab?sid=…&token=…`) |
| Mic check screen | `checkMicrophone()` from `../voice` (returns ok or a reason plus a sentence to show) | `src/student/voice/capture.ts` |
| Page chrome, tables, badges, buttons, modal, error banner | `src/shared/*` | |

Rules that keep AI-written code honest are in `docs/TEAM_PLAN.md` section 5. The short version: use only these types and hooks,
change only the files in your card, add no dependencies, paste the `npm run check` output in the PR.

## Updating the contract types
`docs/openapi.json` is the frozen contract. When it changes: `npm run gen:api` and commit `src/api/schema.ts` (`npm run check` fails on a stale one).

## Tests against the real backend (optional)
`VITE_E2E=1 VITE_API_URL=http://localhost:8000 VITE_E2E_CODE=<a fresh student code> npx vitest run src/api/realBackend.test.ts`

## Voice SDK in one screen of code
```tsx
const voice = useVoiceSession({ sessionId, token })          // token = session.token from useSession()
<Button onClick={() => void voice.connect()}>Start</Button>   // a click: browsers allow audio only after a gesture
<Button onPointerDown={voice.pressToTalk} onPointerUp={voice.release}>Hold to talk</Button>
voice.serverState   // 'listening' | 'thinking' | 'speaking' | 'ended'   (enable the button only when 'listening')
voice.aiText, voice.transcript, voice.remainingMs, voice.level, voice.micError, voice.error, voice.ended
voice.sendText('...')   // typing fallback: also the way forward when voice.micError is set
```
Backend for it: `VOICE_PROVIDER=stub scripts/run_local.sh` (no models; the AI answers with a tone). Protocol: `docs/VOICE_PROTOCOL.md`.
