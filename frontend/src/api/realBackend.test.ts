// Runs the typed client against a REAL backend (scripts/run_local.sh). Skipped unless VITE_E2E=1.
//   VITE_E2E=1 VITE_API_URL=http://localhost:8000 VITE_E2E_CODE=<a fresh LOCAL02 code> npx vitest run src/api/realBackend.test.ts
import { describe, expect, it } from 'vitest'
import { facultyApi } from './faculty'
import { studentApi } from './student'

const enabled = import.meta.env.VITE_E2E === '1'
const base = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const original = globalThis.fetch

describe.skipIf(!enabled)('typed client against the real backend', () => {
  it('faculty can list vivas and sessions with the documented shapes', async () => {
    const api = facultyApi(import.meta.env.VITE_E2E_FACULTY_TOKEN ?? 'demo-token-0123456789', original)
    const vivas = await api.listVivas()
    expect(vivas.items.some((v) => v.id === 'local-dsa')).toBe(true)
    const sessions = await api.listSessions('local-dsa', { limit: 5 })
    expect(Array.isArray(sessions.items)).toBe(true)
    const q = await api.listQuestions('local-dsa')
    expect(q.concept_count).toBeGreaterThan(0)
  })

  it('a student can join, consent, start and answer', async () => {
    const code = import.meta.env.VITE_E2E_CODE
    expect(code, 'set VITE_E2E_CODE to a fresh LOCAL student code').toBeTruthy()
    const open = studentApi(null, original)
    const joined = await open.join({ viva_id: 'local-dsa', student_id: import.meta.env.VITE_E2E_STUDENT ?? 'LOCAL02', access_code: code! })
    const api = studentApi(joined.session_token, original)
    await api.consent(joined.session_id, joined.rules_version)
    const started = await api.start(joined.session_id)
    expect(started.turn.text.length).toBeGreaterThan(0)
    const answered = await api.answer(joined.session_id, 'A hash table maps keys to array indexes with a hash function.', 1)
    expect(answered.client_seq).toBe(1)
    const status = await api.status(joined.session_id)
    expect(status.last_client_seq).toBe(1)
    expect(base).toContain('http')
  })
})
