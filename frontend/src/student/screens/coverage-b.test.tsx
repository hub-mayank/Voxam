import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StudentSessionProvider } from '../session/StudentSessionProvider'
import { studentRoutes } from '../routes'

const mocks = vi.hoisted(() => ({ useVoiceSession: vi.fn() }))
vi.mock('../voice', async (orig) => ({ ...(await orig<typeof import('../voice')>()), useVoiceSession: mocks.useVoiceSession }))

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const err = (code: string, status: number) => json({ error: { code, message: code, details: {} } }, status)
const question = { idx: 2, text: 'Question 2', phase: 'fundamentals', ended: false }
type Handler = (body: Record<string, unknown> | null) => Response
function backend(routes: Record<string, Handler>) {
  const log: string[] = []
  const f = (async (url: string, init: RequestInit) => {
    const path = new URL(String(url)).pathname.replace(/\/student\/sessions\/[^/]+/, '/student/sessions/:sid')
    const key = `${init.method} ${path}`
    log.push(key)
    const handler = routes[key]
    if (!handler) throw new Error(`no handler for ${key}`)
    return handler(init.body ? JSON.parse(String(init.body)) : null)
  }) as unknown as typeof fetch
  return { f, log }
}

function Wrap() {
  return <Outlet />
}

function app(fetchImpl: typeof fetch, at = '/student') {
  return render(
    <MemoryRouter initialEntries={[at]}>
      <Routes>
        <Route path="/student" element={<StudentSessionProvider fetchImpl={fetchImpl}><Wrap /></StudentSessionProvider>}>
          {studentRoutes.map((route, index) => route.index
            ? <Route key={index} index element={route.element} />
            : <Route key={index} path={route.path} element={route.element} />)}
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

function savedSession() {
  sessionStorage.setItem('voxam.student.session', JSON.stringify({
    sessionId: 'sid1', token: 'st_abc', vivaTitle: 'DSA viva', rulesText: 'Answer in your own words.', rulesVersion: 'rules-v1', durationMs: 900000,
  }))
}

function voice(overrides: Record<string, unknown> = {}) {
  return {
    connection: 'open', serverState: 'listening', aiSpeaking: false, aiText: 'Question 2',
    transcript: [], remainingMs: 600000, warning: false, level: 0.1, micError: null, error: null, ended: null, latencyMs: null,
    lastClientSeq: 2, connect: vi.fn(), disconnect: vi.fn(), pressToTalk: vi.fn(), release: vi.fn(),
    endTurn: vi.fn(), sendText: vi.fn(), clearError: vi.fn(), ...overrides,
  }
}

beforeEach(() => {
  sessionStorage.clear()
  mocks.useVoiceSession.mockReset()
})
afterEach(cleanup)

describe('student screens: coverage part B', () => {
  it('shows speaker labels and the server closing text in the completed conversation', async () => {
    savedSession()
    const fetchImpl = backend({
      'GET /student/sessions/:sid/status': () => json({
        status: 'in_progress', phase: 'fundamentals', server_now: '', started_at: '', deadline_at: '',
        remaining_ms: 500000, last_client_seq: 2, current_turn: question,
      }),
      'POST /student/sessions/:sid/answer': () => json({
        client_seq: 3, replayed: false, status: 'ended',
        turn: { idx: 3, text: 'Thank you. Your viva is complete.', phase: 'wrapup', ended: true },
        server_now: '', remaining_ms: 0,
      }),
      'GET /student/sessions/:sid/result': () => err('results_not_released', 403),
    }).f
    app(fetchImpl, '/student/viva')

    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'My answer.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send answer' }))
    await screen.findByText('Your viva is complete')

    const transcript = screen.getByRole('list', { name: 'Your conversation' })
    expect(transcript.textContent).toContain('Interviewer: Question 2')
    expect(transcript.textContent).toContain('You: My answer.')
    expect(transcript.textContent).toContain('Interviewer: Thank you. Your viva is complete.')
    expect(screen.getAllByText('Thank you. Your viva is complete.')).toHaveLength(2)
  })

  it('announces an automatic reconnect and keeps the typed fallback unavailable until voice is open', async () => {
    savedSession()
    mocks.useVoiceSession.mockReturnValue(voice({ connection: 'reconnecting', serverState: 'listening' }))
    const fetchImpl = backend({
      'GET /student/sessions/:sid/status': () => json({
        status: 'in_progress', phase: 'fundamentals', server_now: '', started_at: '', deadline_at: '',
        remaining_ms: 300000, last_client_seq: 2, current_turn: question,
      }),
    }).f
    app(fetchImpl, '/student/viva?mode=hands_free')

    expect((await screen.findByRole('alert')).textContent).toMatch(/Connection lost.*trying to reconnect.*timer may continue/i)
    const answer = screen.getByLabelText('Prefer to type? Write your answer here.') as HTMLTextAreaElement
    fireEvent.change(answer, { target: { value: 'A typed fallback.' } })
    expect((screen.getByRole('button', { name: 'Send typed answer' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('sends a trimmed typed fallback only while listening and clears it after sending', async () => {
    savedSession()
    const session = voice()
    mocks.useVoiceSession.mockReturnValue(session)
    const fetchImpl = backend({
      'GET /student/sessions/:sid/status': () => json({
        status: 'in_progress', phase: 'fundamentals', server_now: '', started_at: '', deadline_at: '',
        remaining_ms: 300000, last_client_seq: 2, current_turn: question,
      }),
    }).f
    app(fetchImpl, '/student/viva?mode=hands_free')

    const answer = await screen.findByLabelText('Prefer to type? Write your answer here.') as HTMLTextAreaElement
    const send = screen.getByRole('button', { name: 'Send typed answer' }) as HTMLButtonElement
    expect(send.disabled).toBe(true)
    fireEvent.change(answer, { target: { value: '  My typed answer.  ' } })
    expect(send.disabled).toBe(false)
    fireEvent.click(send)

    expect(session.sendText).toHaveBeenCalledWith('My typed answer.')
    expect(answer.value).toBe('')
  })

  it('explains a microphone failure and a possibly misheard answer without blaming the student', async () => {
    savedSession()
    mocks.useVoiceSession.mockReturnValue(voice({
      micError: { message: 'The microphone stopped.' },
      transcript: [{ role: 'student', text: 'A hash table uses trees.', confidence: 0.5 }],
    }))
    const fetchImpl = backend({
      'GET /student/sessions/:sid/status': () => json({
        status: 'in_progress', phase: 'fundamentals', server_now: '', started_at: '', deadline_at: '',
        remaining_ms: 300000, last_client_seq: 2, current_turn: question,
      }),
    }).f
    app(fetchImpl, '/student/viva?mode=hands_free')

    expect(await screen.findByText('The microphone stopped.')).toBeTruthy()
    expect(screen.getByText('You can keep going by typing your answer below.')).toBeTruthy()
    expect(screen.getByText(/We may have misheard that.*type your answer instead if it is wrong/)).toBeTruthy()
    expect(screen.queryByText(/confidence.*0\.5/i)).toBeNull()
  })

  it('refreshes the session when voice reports an ended state', async () => {
    savedSession()
    const endedVoice = voice({
      connection: 'closed', serverState: 'ended', ended: { status: 'ended', text: 'The viva has ended.' },
    })
    mocks.useVoiceSession.mockReturnValue(endedVoice)
    let statusCalls = 0
    const { f, log } = backend({
      'GET /student/sessions/:sid/status': () => {
        statusCalls += 1
        return json({
          status: statusCalls === 1 ? 'in_progress' : 'ended', phase: 'wrapup', server_now: '', started_at: '', deadline_at: '',
          remaining_ms: statusCalls === 1 ? 100000 : 0, last_client_seq: 3, current_turn: { ...question, ended: true },
        })
      },
      'GET /student/sessions/:sid/result': () => err('results_not_released', 403),
    })
    app(f, '/student/viva?mode=push_to_talk')

    expect(await screen.findByText('Your viva is complete')).toBeTruthy()
    expect(log.filter((line) => line === 'GET /student/sessions/:sid/status')).toHaveLength(2)
  })
})
