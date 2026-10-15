import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StudentSessionProvider } from '../session/StudentSessionProvider'
import { studentRoutes } from '../routes'

const mocks = vi.hoisted(() => ({ checkMicrophone: vi.fn(), useVoiceSession: vi.fn() }))
vi.mock('../voice', async (orig) => ({
  ...(await orig<typeof import('../voice')>()),
  checkMicrophone: mocks.checkMicrophone,
  useVoiceSession: mocks.useVoiceSession,
}))

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const err = (code: string, status: number, details = {}) => json({ error: { code, message: code, details } }, status)
const turn = (idx: number, ended = false) => ({ idx, text: `Question ${idx}`, phase: 'warmup', ended })
const joined = (status = 'created') => ({
  session_id: 'sid1', session_token: 'st_abc', status, resumed: false, viva_title: 'DSA viva', duration_ms: 900000,
  rules_text: 'Answer in your own words.\nNo outside help.', rules_version: 'rules-v1',
})

type Handler = (body: Record<string, unknown> | null) => Response
function backend(routes: Record<string, Handler>) {
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

function Where() {
  const l = useLocation()
  return <p data-testid="where">{l.pathname + l.search}</p>
}

function app(f: typeof fetch, at = '/student') {
  return render(
    <MemoryRouter initialEntries={[at]}>
      <Where />
      <Routes>
        <Route path="/student" element={<StudentSessionProvider fetchImpl={f}><Wrap /></StudentSessionProvider>}>
          {studentRoutes.map((r, i) => (r.index ? <Route key={i} index element={r.element} /> : <Route key={i} path={r.path} element={r.element} />))}
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

function Wrap() {
  return <Outlet />
}

beforeEach(() => {
  sessionStorage.clear()
  mocks.checkMicrophone.mockReset()
  mocks.useVoiceSession.mockReset()
})
afterEach(cleanup)

const type = (label: string | RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })
const click = (target: string | RegExp | HTMLElement) =>
  fireEvent.click(target instanceof HTMLElement ? target : screen.getByRole('button', { name: target }))
const fillJoin = () => {
  type('Viva ID', 'v1')
  type('Student ID', 'S1')
  type('Access code', 'AAAA-1111')
  click('Continue')
}
const where = () => screen.getByTestId('where').textContent

describe('student screens', () => {
  it('a wrong access code keeps the fields, shows a kind sentence and blocks the button for the server-given wait', async () => {
    const { f } = backend({ 'POST /student/join': () => err('rate_limited', 429, { retry_after_ms: 5000 }) })
    app(f)
    fillJoin()
    expect((await screen.findByRole('alert')).textContent).toMatch(/Too many tries/)
    expect(((await screen.findByRole('button', { name: /Wait \d+ s/ })) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByLabelText('Student ID') as HTMLInputElement).value).toBe('S1')
    expect(screen.queryByText(/rate_limited/)).toBeNull()
  })

  it('the access code is hidden until the student asks to show it', async () => {
    app(backend({}).f)
    const code = screen.getByLabelText('Access code')
    expect(code.getAttribute('type')).toBe('password')
    fireEvent.click(screen.getByLabelText('Show the code'))
    expect(code.getAttribute('type')).toBe('text')
  })

  it('joining goes to the rules; consent needs the tick; accepting goes to the ready screen', async () => {
    const { f, log } = backend({
      'POST /student/join': () => json(joined()),
      'POST /student/sessions/:sid/consent': () => json({ status: 'consented', consent_at: '' }),
    })
    app(f)
    fillJoin()
    await screen.findByText('Answer in your own words.')
    expect(where()).toBe('/student/rules')
    const agree = screen.getByRole('button', { name: 'I agree, continue' }) as HTMLButtonElement
    expect(agree.disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(agree)
    await screen.findByText('How will you answer?')
    expect(log.some((l) => l.startsWith('POST /student/sessions/:sid/consent'))).toBe(true)
  })

  it('voice modes stay locked until the microphone check passed; typing never needs it', async () => {
    const { f } = backend({ 'POST /student/join': () => json(joined('consented')) })
    app(f)
    fillJoin()
    const start = (await screen.findByRole('button', { name: 'Start the viva' })) as HTMLButtonElement
    expect(start.disabled).toBe(false) // typing is the default
    fireEvent.click(screen.getByLabelText(/Push to talk/))
    expect((screen.getByRole('button', { name: 'Start the viva' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('link', { name: 'Check my microphone' })).toBeTruthy()
  })

  it('a whole typed viva: start, answer, the interviewer replies, the closing text ends it', async () => {
    let seq = 0
    const { f } = backend({
      'POST /student/join': () => json(joined('consented')),
      'POST /student/sessions/:sid/start': () => json({ status: 'in_progress', started_at: '', deadline_at: '', server_now: '', remaining_ms: 900000, turn: turn(0) }),
      'POST /student/sessions/:sid/answer': () => {
        seq += 1
        const ended = seq === 2
        return json({ client_seq: seq, replayed: false, status: ended ? 'ended' : 'in_progress', turn: turn(seq * 2, ended), server_now: '', remaining_ms: 800000 })
      },
    })
    app(f)
    fillJoin()
    fireEvent.click(await screen.findByRole('button', { name: 'Start the viva' }))
    await screen.findAllByText('Question 0')
    expect(screen.getByRole('timer').textContent).toBe('15:00')
    const send = screen.getByRole('button', { name: 'Send answer' }) as HTMLButtonElement
    expect(send.disabled).toBe(true)
    type('Your answer', 'A hash table maps keys to buckets.')
    fireEvent.click(send)
    await screen.findAllByText('Question 2')
    type('Your answer', 'It is O(1) on average.')
    click('Send answer')
    await screen.findByText('Your viva is complete')
    expect(where()).toBe('/student/done')
  })

  it('a deadline_passed reply locks the viva and shows the closing words, not an error', async () => {
    const { f } = backend({
      'POST /student/join': () => json(joined('in_progress')),
      'GET /student/sessions/:sid/status': () => json({ status: 'in_progress', phase: 'depth', server_now: '', started_at: '', deadline_at: '', remaining_ms: 5000, last_client_seq: 0, current_turn: turn(0) }),
      'POST /student/sessions/:sid/answer': () => err('deadline_passed', 409, { closing_text: 'Time is up. Thank you.' }),
    })
    app(f)
    fillJoin()
    await screen.findByLabelText('Your answer')
    type('Your answer', 'late answer')
    click('Send answer')
    await waitFor(() => expect(where()).toBe('/student/done'))
    expect(screen.getByText('Time is up. Thank you.')).toBeTruthy()
  })

  it('a reload in the middle of the viva restores the question without asking for the code again', async () => {
    sessionStorage.setItem('voxam.student.session', JSON.stringify({
      sessionId: 'sid1', token: 'st_abc', vivaTitle: 'DSA viva', rulesText: 'r', rulesVersion: 'rules-v1', durationMs: 900000,
    }))
    const { f } = backend({
      'GET /student/sessions/:sid/status': () => json({ status: 'in_progress', phase: 'depth', server_now: '', started_at: '', deadline_at: '', remaining_ms: 400000, last_client_seq: 3, current_turn: turn(6) }),
    })
    await act(async () => {
      app(f, '/student/viva')
    })
    await screen.findAllByText('Question 6')
    expect(where()).toBe('/student/viva')
  })

  it('the done screen offers sign out and clears the saved session', async () => {
    sessionStorage.setItem('voxam.student.session', JSON.stringify({
      sessionId: 'sid1', token: 'st_abc', vivaTitle: 'DSA viva', rulesText: 'r', rulesVersion: 'rules-v1', durationMs: 900000,
    }))
    const { f } = backend({
      'GET /student/sessions/:sid/status': () => json({ status: 'ended', phase: 'wrapup', server_now: '', started_at: '', deadline_at: '', remaining_ms: 0, last_client_seq: 9, current_turn: turn(18, true) }),
    })
    app(f, '/student/done')
    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))
    expect(sessionStorage.getItem('voxam.student.session')).toBeNull()
    await screen.findByText('Join your viva')
  })

  const saved = () => sessionStorage.setItem('voxam.student.session', JSON.stringify({
    sessionId: 'sid1', token: 'st_abc', vivaTitle: 'DSA viva', rulesText: 'r', rulesVersion: 'rules-v1', durationMs: 900000,
  }))
  const consented = () => backend({
    'GET /student/sessions/:sid/status': () => json({ status: 'consented', phase: null, server_now: '', started_at: null, deadline_at: null, remaining_ms: null, last_client_seq: 0, current_turn: null }),
  }).f

  it('mic check: a blocked microphone gives plain steps and a way to continue by typing', async () => {
    saved()
    mocks.checkMicrophone.mockResolvedValue({ ok: false, reason: 'denied', message: 'The browser blocked the microphone. Click the lock icon.' })
    app(consented(), '/student/mic-check?mode=push_to_talk')
    click(await screen.findByRole('button', { name: 'Start the check' }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/blocked the microphone/)
    expect(screen.getByText(/still take the viva by typing/)).toBeTruthy()
    click('Type my answers instead')
    await waitFor(() => expect(where()).toBe('/student/ready?mode=text'))
  })

  it('mic check: too quiet is not an accusation and can be retried', async () => {
    saved()
    mocks.checkMicrophone.mockResolvedValue({ ok: true, peak: 0.001 })
    app(consented(), '/student/mic-check?mode=hands_free')
    click(await screen.findByRole('button', { name: 'Start the check' }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/cannot hear you yet/)
    expect(screen.getAllByRole('button', { name: 'Try again' }).length).toBeGreaterThan(0)
    expect(sessionStorage.getItem('voxam.student.mic')).toBeNull()
  })

  it('mic check: a good level passes, remembers it and returns to the ready screen with the chosen mode', async () => {
    saved()
    mocks.checkMicrophone.mockResolvedValue({ ok: true, peak: 0.2 })
    app(consented(), '/student/mic-check?mode=hands_free')
    click(await screen.findByRole('button', { name: 'Start the check' }))
    click(await screen.findByRole('button', { name: 'Continue' })) // jsdom has no MediaRecorder: the sample step is skipped
    await waitFor(() => expect(where()).toBe('/student/ready?mode=hands_free'))
    expect(sessionStorage.getItem('voxam.student.mic')).toBe('1')
  })

  it('voice viva: hold to talk presses and releases, and works while the interviewer is speaking (barge-in)', async () => {
    saved()
    const voice = {
      connection: 'open', serverState: 'listening', aiSpeaking: false, aiText: 'Explain a hash table.', transcript: [], remainingMs: 600000,
      warning: false, level: 0.1, micError: null, error: null, ended: null, latencyMs: null,
      connect: vi.fn(), disconnect: vi.fn(), pressToTalk: vi.fn(), release: vi.fn(), endTurn: vi.fn(), sendText: vi.fn(), clearError: vi.fn(),
    }
    mocks.useVoiceSession.mockReturnValue(voice)
    const f = backend({
      'GET /student/sessions/:sid/status': () => json({ status: 'in_progress', phase: 'depth', server_now: '', started_at: '', deadline_at: '', remaining_ms: 600000, last_client_seq: 0, current_turn: turn(0) }),
    }).f
    app(f, '/student/viva?mode=push_to_talk')
    const talk = (await screen.findByRole('button', { name: 'Hold to talk' })) as HTMLButtonElement
    expect(talk.disabled).toBe(false)
    fireEvent.pointerDown(talk)
    expect(voice.pressToTalk).toHaveBeenCalledTimes(1)
    fireEvent.pointerUp(await screen.findByRole('button', { name: 'Release when you are done' }))
    expect(voice.release).toHaveBeenCalledTimes(1)
    // the interviewer is speaking: the button stays available (barge-in)
    mocks.useVoiceSession.mockReturnValue({ ...voice, serverState: 'speaking', aiSpeaking: true })
    cleanup()
    app(f, '/student/viva?mode=push_to_talk')
    const blocked = (await screen.findByRole('button', { name: 'Hold to talk' })) as HTMLButtonElement
    expect(blocked.disabled).toBe(false)
    expect(screen.getByText('The interviewer is speaking')).toBeTruthy()
  })

  it('voice viva: a lost connection says so honestly and offers to reconnect', async () => {
    saved()
    mocks.useVoiceSession.mockReturnValue({
      connection: 'closed', serverState: null, aiSpeaking: false, aiText: '', transcript: [], remainingMs: 300000, warning: false, level: 0,
      micError: null, error: null, ended: null, latencyMs: null, connect: vi.fn(), disconnect: vi.fn(), pressToTalk: vi.fn(),
      release: vi.fn(), endTurn: vi.fn(), sendText: vi.fn(), clearError: vi.fn(),
    })
    const f = backend({
      'GET /student/sessions/:sid/status': () => json({ status: 'in_progress', phase: 'depth', server_now: '', started_at: '', deadline_at: '', remaining_ms: 300000, last_client_seq: 0, current_turn: turn(0) }),
    }).f
    app(f, '/student/viva?mode=hands_free')
    expect((await screen.findByRole('alert')).textContent).toMatch(/voice connection closed/)
    expect(screen.getByRole('button', { name: 'Reconnect' })).toBeTruthy()
    expect(screen.getByLabelText(/Prefer to type/)).toBeTruthy()
  })

  it('a session the server no longer accepts offers to sign in again instead of a dead end', async () => {
    saved()
    const f = backend({
      'GET /student/sessions/:sid/status': () => json({ status: 'consented', phase: null, server_now: '', started_at: null, deadline_at: null, remaining_ms: null, last_client_seq: 0, current_turn: null }),
      'POST /student/sessions/:sid/start': () => err('unauthorized', 401, { reason: 'replaced' }),
    }).f
    app(f, '/student/ready')
    click(await screen.findByRole('button', { name: 'Start the viva' }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/sign in again/i)
    click('Sign in again')
    await screen.findByText('Join your viva')
    expect(sessionStorage.getItem('voxam.student.session')).toBeNull()
  })

  const ended = () => ({
    'GET /student/sessions/:sid/status': () => json({ status: 'scored', phase: 'wrapup', server_now: '', started_at: '', deadline_at: '', remaining_ms: 0, last_client_seq: 9, current_turn: turn(18, true) }),
  })
  const resultBody = (overridden = false) => ({
    total: 72.5, overridden, feedback: [{ text: 'Explain collisions with an example.', evidence: [3, 5] }],
    dimensions: [{ key: 'conceptual', weight: 30, score: 4 }, { key: 'communication', weight: 10, score: 3 }],
  })

  it('done: a released result shows the total, each dimension in words and the feedback with its turns', async () => {
    saved()
    app(backend({ ...ended(), 'GET /student/sessions/:sid/result': () => json(resultBody()) }).f, '/student/done')
    await screen.findByText('Your result: 72.5 / 100')
    expect(screen.getByText(/Conceptual understanding: 4 \/ 5/)).toBeTruthy()
    expect(screen.getByText(/Communication: 3 \/ 5/)).toBeTruthy()
    expect(screen.getByText(/Explain collisions/)).toBeTruthy()
    expect(screen.getByText(/turns 3, 5/)).toBeTruthy()
  })

  it('done: an overridden total says a person changed it', async () => {
    saved()
    app(backend({ ...ended(), 'GET /student/sessions/:sid/result': () => json(resultBody(true)) }).f, '/student/done')
    await screen.findByText(/A faculty member changed your total/)
  })

  it('done: not released and still being marked are kind messages and can be asked again', async () => {
    saved()
    let calls = 0
    const f = backend({
      ...ended(),
      'GET /student/sessions/:sid/result': () => {
        calls += 1
        return calls === 1 ? err('results_not_released', 403) : calls === 2 ? err('invalid_state', 409, { status: 'scoring' }) : json(resultBody())
      },
    }).f
    app(f, '/student/done')
    await screen.findByText(/has not been released yet/)
    click('Check again')
    await screen.findByText(/still being marked/)
    click('Check again')
    await screen.findByText('Your result: 72.5 / 100')
  })
})
