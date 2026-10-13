import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useStudentSession } from './useStudentSession'

type Handler = (body: Record<string, unknown> | null) => Response | Promise<Response>

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const err = (code: string, status: number, details = {}) => json({ error: { code, message: code, details } }, status)

function server(routes: Record<string, Handler>) {
  const log: string[] = []
  const f = (async (url: string, init: RequestInit) => {
    const path = new URL(String(url)).pathname.replace(/\/student\/sessions\/[^/]+/, '/student/sessions/:sid')
    const key = `${init.method} ${path}`
    log.push(init.body ? `${key} ${init.body}` : key)
    const h = routes[key]
    if (!h) throw new Error(`no handler for ${key}`)
    return h(init.body ? JSON.parse(String(init.body)) : null)
  }) as unknown as typeof fetch
  return { f, log }
}

const joinRes = (status = 'created') => ({
  session_id: 'sid1', session_token: 'st_abc', status, resumed: false, viva_title: 'DSA', duration_ms: 900000, rules_text: 'rules', rules_version: 'rules-v1',
})
const turn = (idx: number, ended = false) => ({ idx, text: `q${idx}`, phase: 'warmup', ended })
const answerRes = (seq: number, ended = false) => ({ client_seq: seq, replayed: false, status: 'in_progress', turn: turn(seq * 2, ended), server_now: '', remaining_ms: 800000 })

beforeEach(() => sessionStorage.clear())

describe('useStudentSession', () => {
  it('joins, consents, starts and answers', async () => {
    const { f, log } = server({
      'POST /student/join': () => json(joinRes()),
      'POST /student/sessions/:sid/consent': () => json({ status: 'consented', consent_at: '' }),
      'POST /student/sessions/:sid/start': () => json({ status: 'in_progress', started_at: '', deadline_at: '', server_now: '', remaining_ms: 900000, turn: turn(0) }),
      'POST /student/sessions/:sid/answer': () => json(answerRes(1)),
    })
    const { result } = renderHook(() => useStudentSession(f))
    await act(() => result.current.join('v', 'S1', 'AAAA-1111'))
    expect(result.current.phase).toBe('rules')
    await act(() => result.current.accept())
    await act(() => result.current.start())
    expect(result.current).toMatchObject({ phase: 'viva', currentTurn: { idx: 0 } })
    expect(result.current.remainingMs).toBeGreaterThan(890000)
    let ok = false
    await act(async () => { ok = await result.current.submitAnswer('  a hash table  ') })
    expect(ok).toBe(true)
    expect(result.current.lastSeq).toBe(1)
    expect(log.at(-1)).toContain('"text":"a hash table","client_seq":1')
  })

  it('retries a failed answer with the SAME client_seq', async () => {
    let calls = 0
    const { f, log } = server({
      'POST /student/join': () => json(joinRes('in_progress')),
      'GET /student/sessions/:sid/status': () => json({ status: 'in_progress', phase: 'warmup', server_now: '', remaining_ms: 800000, last_client_seq: 0, current_turn: turn(0) }),
      'POST /student/sessions/:sid/answer': () => (++calls === 1 ? err('provider_unavailable', 503, { retry_after_ms: 3000 }) : json(answerRes(1))),
    })
    const { result } = renderHook(() => useStudentSession(f))
    await act(() => result.current.join('v', 'S1', 'c'))
    let ok = true
    await act(async () => { ok = await result.current.submitAnswer('my answer') })
    expect(ok).toBe(false)
    expect(result.current.error?.code).toBe('provider_unavailable')
    await act(async () => { ok = await result.current.submitAnswer('my answer') })
    expect(ok).toBe(true)
    const seqs = log.filter((l) => l.includes('/answer')).map((l) => JSON.parse(l.split('/answer ')[1]).client_seq)
    expect(seqs).toEqual([1, 1])
  })

  it('resyncs from the server after bad_client_seq', async () => {
    const { f } = server({
      'POST /student/join': () => json(joinRes('in_progress')),
      'GET /student/sessions/:sid/status': () => json({ status: 'in_progress', phase: 'depth', server_now: '', remaining_ms: 700000, last_client_seq: 4, current_turn: turn(8) }),
      'POST /student/sessions/:sid/answer': () => err('bad_client_seq', 409, { expected: 5, received: 1 }),
    })
    const { result } = renderHook(() => useStudentSession(f))
    await act(() => result.current.join('v', 'S1', 'c'))
    await act(async () => { await result.current.submitAnswer('x') })
    expect(result.current.lastSeq).toBe(4)
    expect(result.current.error?.code).toBe('bad_client_seq')
  })

  it('ends the viva with the closing text on deadline_passed', async () => {
    const { f } = server({
      'POST /student/join': () => json(joinRes('in_progress')),
      'GET /student/sessions/:sid/status': () => json({ status: 'in_progress', phase: 'depth', server_now: '', remaining_ms: 1, last_client_seq: 3, current_turn: turn(6) }),
      'POST /student/sessions/:sid/answer': () => err('deadline_passed', 409, { closing_text: 'Time is up. Thank you.' }),
    })
    const { result } = renderHook(() => useStudentSession(f))
    await act(() => result.current.join('v', 'S1', 'c'))
    await act(async () => { await result.current.submitAnswer('late') })
    expect(result.current).toMatchObject({ phase: 'done', closingText: 'Time is up. Thank you.' })
  })

  it('resumes a saved session after a reload', async () => {
    sessionStorage.setItem('voxam.student.session', JSON.stringify({ sessionId: 'sid1', token: 'st_abc' }))
    const { f } = server({
      'GET /student/sessions/:sid/status': () => json({ status: 'in_progress', phase: 'depth', server_now: '', remaining_ms: 600000, last_client_seq: 6, current_turn: turn(12) }),
    })
    const { result } = renderHook(() => useStudentSession(f))
    await waitFor(() => expect(result.current.phase).toBe('viva'))
    expect(result.current).toMatchObject({ lastSeq: 6, sessionId: 'sid1' })
  })

  it('shows a wrong code as an error and stays on login', async () => {
    const { f } = server({ 'POST /student/join': () => err('invalid_credentials', 403) })
    const { result } = renderHook(() => useStudentSession(f))
    await act(() => result.current.join('v', 'S1', 'nope'))
    expect(result.current).toMatchObject({ phase: 'login', busy: false })
    expect(result.current.error?.code).toBe('invalid_credentials')
  })
})
