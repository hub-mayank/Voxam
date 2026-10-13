import { describe, expect, it } from 'vitest'
import { ApiError } from '../../api/client'
import type { AnswerResponse, JoinResponse, StartResponse, StatusResponse } from '../../api/types'
import { initialState, reducer } from './state'

const join = (status: JoinResponse['status']): JoinResponse => ({
  session_id: 's1', session_token: 'st_x', status, resumed: false, viva_title: 'DSA', duration_ms: 900000,
  rules_text: 'rules', rules_version: 'rules-v1',
})
const turn = (idx: number, ended = false) => ({ idx, text: `q${idx}`, phase: 'warmup', ended })

describe('student session reducer', () => {
  it('walks login -> rules -> ready -> viva -> done', () => {
    let s = reducer(initialState, { type: 'joined', res: join('created') })
    expect(s.phase).toBe('rules')
    s = reducer(s, { type: 'consented' })
    expect(s.phase).toBe('ready')
    const start: StartResponse = { status: 'in_progress', started_at: '', deadline_at: '', server_now: '', remaining_ms: 900000, turn: turn(0) }
    s = reducer(s, { type: 'started', res: start, now: 1000 })
    expect(s).toMatchObject({ phase: 'viva', deadlineMs: 901000, currentTurn: { idx: 0 } })
    const ans: AnswerResponse = { client_seq: 1, replayed: false, status: 'in_progress', turn: turn(2), server_now: '', remaining_ms: 850000 }
    s = reducer(s, { type: 'answered', res: ans, text: 'hi', now: 5000 })
    expect(s).toMatchObject({ lastSeq: 1, deadlineMs: 855000, phase: 'viva' })
    expect(s.transcript.map((t) => t.role)).toEqual(['ai', 'student', 'ai'])
    s = reducer(s, { type: 'answered', res: { ...ans, client_seq: 2, turn: turn(4, true) }, text: 'bye', now: 6000 })
    expect(s).toMatchObject({ phase: 'done', closingText: 'q4' })
  })

  it('does not duplicate transcript lines for a replayed answer', () => {
    let s = reducer(initialState, { type: 'joined', res: join('in_progress') })
    const ans: AnswerResponse = { client_seq: 1, replayed: true, status: 'in_progress', turn: turn(2), server_now: '', remaining_ms: 1 }
    s = reducer(s, { type: 'answered', res: ans, text: 'hi', now: 0 })
    expect(s.transcript).toEqual([])
  })

  it('resumes from status: the server count wins, an over session is done', () => {
    const st: StatusResponse = { status: 'in_progress', phase: 'depth', server_now: '', started_at: '', deadline_at: '', remaining_ms: 5000,
      last_client_seq: 7, current_turn: turn(14) }
    let s = reducer({ ...initialState, lastSeq: 2 }, { type: 'status', res: st, now: 100 })
    expect(s).toMatchObject({ phase: 'viva', lastSeq: 7, deadlineMs: 5100 })
    s = reducer(s, { type: 'status', res: { ...st, status: 'scored', remaining_ms: 0 }, now: 200 })
    expect(s.phase).toBe('done')
  })

  it('keeps an error until it is cleared', () => {
    const err = new ApiError('invalid_credentials', 'Wrong ID or code.', 403)
    let s = reducer(initialState, { type: 'failed', error: err })
    expect(s.error).toBe(err)
    s = reducer(s, { type: 'clear_error' })
    expect(s.error).toBeNull()
  })
})
