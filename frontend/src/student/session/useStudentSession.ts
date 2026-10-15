// Everything a student screen needs, with the tricky parts handled once (docs/API.md):
//  - answers are idempotent on client_seq: a retry after a timeout resends the SAME seq and text, never a new one;
//  - the countdown is driven by the server's remaining_ms (re-synced on every response), not by the client clock alone;
//  - a reload resumes the same session from sessionStorage + GET status;
//  - closing text from deadline_passed ends the viva cleanly.
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { studentApi } from '../../api/student'
import type { StudentResult } from '../../api/types'
import { initialState, reducer, type SessionState } from './state'

const KEY = 'voxam.student.session'

interface Saved {
  sessionId: string
  token: string
  vivaTitle: string
  rulesText: string
  rulesVersion: string
  durationMs: number
}

function load(): Saved | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function save(v: Saved | null) {
  try {
    if (v) sessionStorage.setItem(KEY, JSON.stringify(v))
    else sessionStorage.removeItem(KEY)
  } catch {
    // storage blocked: reload will ask for the login again
  }
}

export interface StudentSession extends SessionState {
  /** milliseconds left, 0 when over, null before start. Updates 4 times a second. */
  remainingMs: number | null
  /** true while a saved session is being re-read after a reload: screens should wait before redirecting */
  restoring: boolean
  join: (vivaId: string, studentId: string, accessCode: string) => Promise<void>
  /** accept the rules and recording (consent) */
  accept: () => Promise<void>
  /** start the clock; returns after the first question is available */
  start: () => Promise<void>
  /** send a typed answer; resolves true when it was accepted */
  submitAnswer: (text: string) => Promise<boolean>
  /** re-read status (after a reload, or when the timer looks wrong) */
  refresh: () => Promise<void>
  /** the student's own result; rejects with results_not_released or invalid_state (not scored yet) */
  result: () => Promise<StudentResult>
  clearError: () => void
  signOut: () => void
}

export function useStudentSession(fetchImpl?: typeof fetch): StudentSession {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [now, setNow] = useState(() => Date.now())
  const [restoring, setRestoring] = useState(() => load() !== null)
  const pending = useRef<{ text: string; seq: number } | null>(null)
  const api = useMemo(() => studentApi(state.token, fetchImpl), [state.token, fetchImpl])

  const fail = useCallback((e: unknown) => {
    const err = e instanceof ApiError ? e : new ApiError('internal_error', e instanceof Error ? e.message : 'Unexpected error', 0)
    dispatch({ type: 'failed', error: err })
    return err
  }, [])

  const join = useCallback(async (vivaId: string, studentId: string, accessCode: string) => {
    dispatch({ type: 'busy', busy: true })
    try {
      const res = await studentApi(null, fetchImpl).join({ viva_id: vivaId.trim(), student_id: studentId.trim(), access_code: accessCode.trim() })
      save({ sessionId: res.session_id, token: res.session_token, vivaTitle: res.viva_title, rulesText: res.rules_text,
        rulesVersion: res.rules_version, durationMs: res.duration_ms })
      dispatch({ type: 'joined', res })
      if (res.status === 'in_progress') {
        const st = await studentApi(res.session_token, fetchImpl).status(res.session_id)
        dispatch({ type: 'status', res: st, now: Date.now() })
      }
    } catch (e) {
      fail(e)
    }
  }, [fail, fetchImpl])

  const accept = useCallback(async () => {
    if (!state.sessionId) return
    dispatch({ type: 'busy', busy: true })
    try {
      await api.consent(state.sessionId, state.rulesVersion)
      dispatch({ type: 'consented' })
    } catch (e) {
      fail(e)
    }
  }, [api, state.sessionId, state.rulesVersion, fail])

  const start = useCallback(async () => {
    if (!state.sessionId) return
    dispatch({ type: 'busy', busy: true })
    try {
      dispatch({ type: 'started', res: await api.start(state.sessionId), now: Date.now() })
    } catch (e) {
      fail(e)
    }
  }, [api, state.sessionId, fail])

  const submitAnswer = useCallback(async (text: string) => {
    if (!state.sessionId) return false
    const clean = text.trim()
    if (!clean) return false
    // a retry of the same text reuses the pending seq; a different text is a new answer
    const same = pending.current && pending.current.text === clean
    const seq = same ? pending.current!.seq : state.lastSeq + 1
    pending.current = { text: clean, seq }
    dispatch({ type: 'busy', busy: true })
    try {
      const res = await api.answer(state.sessionId, clean, seq)
      pending.current = null
      dispatch({ type: 'answered', res, text: clean, now: Date.now() })
      return true
    } catch (e) {
      const err = fail(e)
      if (err.code === 'deadline_passed') {
        pending.current = null
        const closing = typeof err.details.closing_text === 'string' ? err.details.closing_text : null
        dispatch({ type: 'ended', closingText: closing })
      } else if (err.code === 'session_ended') {
        pending.current = null
        dispatch({ type: 'ended', closingText: null })
      } else if (err.code === 'bad_client_seq' && state.sessionId) {
        pending.current = null // the server's count is the truth: re-read it
        try {
          dispatch({ type: 'status', res: await api.status(state.sessionId), now: Date.now() })
        } catch {
          // the error above stays visible
        }
      }
      return false
    }
  }, [api, state.sessionId, state.lastSeq, fail])

  const refresh = useCallback(async () => {
    if (!state.sessionId) return
    try {
      dispatch({ type: 'status', res: await api.status(state.sessionId), now: Date.now() })
    } catch (e) {
      fail(e)
    }
  }, [api, state.sessionId, fail])

  const result = useCallback(() => api.result(state.sessionId ?? ''), [api, state.sessionId])

  // the server says this step is not allowed now: read where the session really is and move to that screen
  useEffect(() => {
    if (state.error?.code === 'invalid_state' && state.sessionId) void refresh()
  }, [state.error])

  // resume after a reload
  useEffect(() => {
    const saved = load()
    if (!saved) return
    const a = studentApi(saved.token, fetchImpl)
    a.status(saved.sessionId).then(
      (st) => {
        dispatch({ type: 'joined', res: { session_id: saved.sessionId, session_token: saved.token, status: st.status, resumed: true,
          viva_title: saved.vivaTitle, duration_ms: saved.durationMs, rules_text: saved.rulesText, rules_version: saved.rulesVersion } })
        dispatch({ type: 'status', res: st, now: Date.now() })
        setRestoring(false)
      },
      () => {
        save(null)
        setRestoring(false)
      },
    )
  }, [fetchImpl])

  // countdown
  useEffect(() => {
    if (state.phase !== 'viva') return
    setNow(Date.now()) // the first paint must not use a clock value from before the start
    const id = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(id)
  }, [state.phase])

  const remainingMs = state.deadlineMs === null ? null : Math.max(0, state.deadlineMs - now)

  return {
    ...state, remainingMs, restoring, join, accept, start, submitAnswer, refresh, result,
    clearError: () => dispatch({ type: 'clear_error' }),
    signOut: () => { save(null); pending.current = null; dispatch({ type: 'reset' }) },
  }
}
