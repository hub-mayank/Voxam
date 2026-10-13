// @vitest-environment node
// Runs the typed client against a REAL backend (scripts/run_local.sh). Skipped unless VITE_E2E=1.
//   VITE_E2E=1 VITE_API_URL=http://localhost:8000 VITE_E2E_CODE=<a fresh LOCAL02 code> npx vitest run src/api/realBackend.test.ts
import { describe, expect, it } from 'vitest'
import { facultyApi } from './faculty'
import { studentApi } from './student'
import { VoiceClient } from '../student/voice/client'
import { floatToPcm16 } from '../student/voice/pcm'

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

  it('the voice client completes a push-to-talk turn over the real WebSocket (stub or local speech)', async () => {
    const code = import.meta.env.VITE_E2E_VOICE_CODE
    expect(code, 'set VITE_E2E_VOICE_CODE to a fresh code for VITE_E2E_VOICE_STUDENT (default LOCAL03)').toBeTruthy()
    const joined = await studentApi(null, original).join({ viva_id: 'local-dsa', student_id: import.meta.env.VITE_E2E_VOICE_STUDENT ?? 'LOCAL03', access_code: code! })
    const api = studentApi(joined.session_token, original)
    await api.consent(joined.session_id, joined.rules_version)
    await api.start(joined.session_id)
    const log: string[] = []
    let audioBytes = 0
    let transcript = ''
    const done = new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`timed out; saw ${log.join(',')}`)), 20000)
      const client: VoiceClient = new VoiceClient({
        url: `${base.replace(/^http/, 'ws')}/student/sessions/${joined.session_id}/voice`, token: joined.session_token,
        events: {
          onReady: () => log.push('ready'),
          onAiTurn: (t) => log.push(`ai_turn:${t.idx}`),
          onAudio: (pcm) => { audioBytes += pcm.length * 2 },
          onState: (s) => {
            log.push(`state:${s}`)
            if (s === 'listening' && !log.includes('spoke')) {
              log.push('spoke')
              client.pressToTalk()
              const tone = new Float32Array(16000).map((_, i) => 0.4 * Math.sin((2 * Math.PI * 300 * i) / 16000))
              const pcm = floatToPcm16(tone)
              for (let i = 0; i < pcm.length; i += 320) client.sendAudio(pcm.slice(i, i + 320))
              client.release()
            }
          },
          onTranscript: (t) => { transcript = t.text },
          onError: (e) => { clearTimeout(timer); reject(new Error(`server error ${e.code}: ${e.message}`)) },
        },
      })
      client.connect()
      const check = setInterval(() => {
        if (transcript && log.filter((l) => l.startsWith('ai_turn')).length >= 2) {
          clearInterval(check)
          clearTimeout(timer)
          client.disconnect()
          resolve()
        }
      }, 100)
    })
    await done
    expect(log[0]).toBe('ready')
    expect(transcript.length).toBeGreaterThan(0)
    expect(audioBytes).toBeGreaterThan(1000)
  }, 30000)
})

