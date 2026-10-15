// The student's viva state as a plain reducer (easy to test, no React). useStudentSession() wires it to the API.
import type { ApiError } from '../../api/client'
import type { AiTurn, AnswerResponse, JoinResponse, StartResponse, StatusResponse } from '../../api/types'

export type Phase = 'login' | 'rules' | 'ready' | 'viva' | 'done'

export interface TranscriptLine {
  role: 'ai' | 'student'
  text: string
}

export interface SessionState {
  phase: Phase
  sessionId: string | null
  token: string | null
  vivaTitle: string
  rulesText: string
  rulesVersion: string
  durationMs: number
  /** the AI turn the student is answering now */
  currentTurn: AiTurn | null
  /** highest client_seq the server has accepted */
  lastSeq: number
  /** server deadline as epoch ms, corrected for the server/client clock difference */
  deadlineMs: number | null
  transcript: TranscriptLine[]
  /** closing text when the viva ended (including deadline_passed) */
  closingText: string | null
  busy: boolean
  error: ApiError | null
}

export const initialState: SessionState = {
  phase: 'login', sessionId: null, token: null, vivaTitle: '', rulesText: '', rulesVersion: '', durationMs: 0,
  currentTurn: null, lastSeq: 0, deadlineMs: null, transcript: [], closingText: null, busy: false, error: null,
}

export type Event =
  | { type: 'busy'; busy: boolean }
  | { type: 'failed'; error: ApiError }
  | { type: 'joined'; res: JoinResponse }
  | { type: 'consented' }
  | { type: 'started'; res: StartResponse; now: number }
  | { type: 'answered'; res: AnswerResponse; text: string; now: number }
  | { type: 'voice_sequence'; lastSeq: number }
  | { type: 'status'; res: StatusResponse; now: number }
  | { type: 'ended'; closingText: string | null }
  | { type: 'clear_error' }
  | { type: 'reset' }

/** The deadline on the client's clock. remaining_ms is computed on the server's clock, so adding it to our "now" needs no skew fix. */
function deadlineOn(clientNow: number, remainingMs: number | null | undefined): number | null {
  return remainingMs === null || remainingMs === undefined ? null : clientNow + remainingMs
}

export function reducer(s: SessionState, e: Event): SessionState {
  switch (e.type) {
    case 'busy':
      return { ...s, busy: e.busy }
    case 'failed':
      return { ...s, busy: false, error: e.error }
    case 'clear_error':
      return { ...s, error: null }
    case 'reset':
      return initialState
    case 'joined': {
      const phase: Phase = e.res.status === 'created' ? 'rules' : e.res.status === 'consented' ? 'ready' : 'viva'
      return {
        ...s, phase, sessionId: e.res.session_id, token: e.res.session_token, vivaTitle: e.res.viva_title, rulesText: e.res.rules_text,
        rulesVersion: e.res.rules_version, durationMs: e.res.duration_ms, busy: false, error: null,
      }
    }
    case 'consented':
      return { ...s, phase: 'ready', busy: false, error: null }
    case 'started':
      return {
        ...s, phase: 'viva', currentTurn: e.res.turn, deadlineMs: deadlineOn(e.now, e.res.remaining_ms),
        transcript: s.transcript.length ? s.transcript : [{ role: 'ai', text: e.res.turn.text }], busy: false, error: null,
      }
    case 'answered': {
      const lines: TranscriptLine[] = e.res.replayed ? [] : [{ role: 'student', text: e.text }, { role: 'ai', text: e.res.turn.text }]
      const ended = e.res.turn.ended
      return {
        ...s, lastSeq: Math.max(s.lastSeq, e.res.client_seq), currentTurn: e.res.turn, phase: ended ? 'done' : 'viva',
        deadlineMs: deadlineOn(e.now, e.res.remaining_ms), transcript: [...s.transcript, ...lines],
        closingText: ended ? e.res.turn.text : s.closingText, busy: false, error: null,
      }
    }
    case 'voice_sequence':
      return { ...s, lastSeq: Math.max(s.lastSeq, e.lastSeq) }
    case 'status': {
      const byStatus: Partial<Record<string, Phase>> = { created: 'rules', consented: 'ready', in_progress: 'viva' }
      const phase: Phase = byStatus[e.res.status] ?? 'done' // ended, scoring, scored, abandoned, failed: nothing more to do
      const turn = e.res.current_turn ?? s.currentTurn
      return {
        ...s, phase, lastSeq: e.res.last_client_seq, currentTurn: turn, deadlineMs: deadlineOn(e.now, e.res.remaining_ms),
        transcript: s.transcript.length || !turn ? s.transcript : [{ role: 'ai', text: turn.text }], busy: false,
      }
    }
    case 'ended':
      return { ...s, phase: 'done', closingText: e.closingText ?? s.closingText, busy: false, error: null }
  }
}
