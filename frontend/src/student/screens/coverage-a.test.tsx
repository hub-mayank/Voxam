import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StudentSessionProvider } from '../session/StudentSessionProvider'
import { studentRoutes } from '../routes'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const err = (code: string, status: number) => json({ error: { code, message: code, details: {} } }, status)
const turn = { idx: 2, text: 'Explain a hash table.', phase: 'fundamentals', ended: false }
const joined = (status = 'created', rulesText = 'Answer in your own words.\n\nNo outside help.') => ({
  session_id: 'sid1', session_token: 'st_abc', status, resumed: false, viva_title: 'DSA viva', duration_ms: 900000,
  rules_text: rulesText, rules_version: 'rules-v1',
})

type Handler = (body: Record<string, unknown> | null) => Response
function backend(routes: Record<string, Handler>) {
  const log: string[] = []
  const f = (async (url: string, init: RequestInit) => {
    const path = new URL(String(url)).pathname.replace(/\/student\/sessions\/[^/]+/, '/student/sessions/:sid')
    const key = `${init.method} ${path}`
    log.push(init.body ? `${key} ${init.body}` : key)
    const handler = routes[key]
    if (!handler) throw new Error(`no handler for ${key}`)
    return handler(init.body ? JSON.parse(String(init.body)) : null)
  }) as unknown as typeof fetch
  return { f, log }
}

function Where() {
  const location = useLocation()
  return <p data-testid="where">{location.pathname + location.search}</p>
}

function Wrap() {
  return <Outlet />
}

function app(fetchImpl: typeof fetch, at = '/student') {
  return render(
    <MemoryRouter initialEntries={[at]}>
      <Where />
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

beforeEach(() => sessionStorage.clear())
afterEach(cleanup)

describe('student screens: coverage part A', () => {
  it('prefills the viva from the link and keeps Continue disabled while joining is pending', async () => {
    let resolveJoin: ((response: Response) => void) | undefined
    const fetchImpl = vi.fn(() => new Promise<Response>((resolve) => { resolveJoin = resolve })) as unknown as typeof fetch
    app(fetchImpl, '/student?viva=local-dsa')

    expect((screen.getByLabelText('Viva ID') as HTMLInputElement).value).toBe('local-dsa')
    fireEvent.change(screen.getByLabelText('Student ID'), { target: { value: 'S1' } })
    fireEvent.change(screen.getByLabelText('Access code'), { target: { value: 'AAAA-1111' } })
    const continueButton = screen.getByRole('button', { name: 'Continue' }) as HTMLButtonElement
    expect(continueButton.disabled).toBe(false)
    fireEvent.click(continueButton)
    expect((screen.getByRole('button', { name: 'Continue' }) as HTMLButtonElement).disabled).toBe(true)

    await act(async () => resolveJoin?.(json(joined())))
    await screen.findByText('Answer in your own words.')
  })

  it('shows the server rules as separate paragraphs with the viva title and duration', async () => {
    const fetchImpl = backend({ 'POST /student/join': () => json(joined('created')) }).f
    app(fetchImpl)
    fireEvent.change(screen.getByLabelText('Viva ID'), { target: { value: 'v1' } })
    fireEvent.change(screen.getByLabelText('Student ID'), { target: { value: 'S1' } })
    fireEvent.change(screen.getByLabelText('Access code'), { target: { value: 'AAAA-1111' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    expect(await screen.findByRole('heading', { name: 'DSA viva' })).toBeTruthy()
    expect(screen.getByText('Answer in your own words.')).toBeTruthy()
    expect(screen.getByText('No outside help.')).toBeTruthy()
    expect(screen.getByText(/15 minutes.*voice or by typing/)).toBeTruthy()
  })

  it('keeps the selected voice mode in the URL and unlocks Start after a microphone check', async () => {
    savedSession()
    sessionStorage.setItem('voxam.student.mic', '1')
    const fetchImpl = backend({
      'GET /student/sessions/:sid/status': () => json({
        status: 'consented', phase: null, server_now: '', started_at: null, deadline_at: null,
        remaining_ms: null, last_client_seq: 0, current_turn: null,
      }),
    }).f
    app(fetchImpl, '/student/ready?mode=hands_free')

    expect(await screen.findByText('Microphone checked.')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Start the viva' }) as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(screen.getByLabelText(/Push to talk/))
    const search = new URLSearchParams(screen.getByTestId('where').textContent?.split('?')[1])
    expect(search.get('mode')).toBe('push_to_talk')
    expect(search.get('lang')).toBe('en')
    expect(screen.getByText(/15-minute clock starts when you press Start/)).toBeTruthy()
  })

  it('keeps a typed answer after a temporary failure and retries with the same sequence', async () => {
    const { f, log } = backend({
      'POST /student/join': () => json(joined('in_progress')),
      'GET /student/sessions/:sid/status': () => json({
        status: 'in_progress', phase: 'fundamentals', server_now: '', started_at: '', deadline_at: '',
        remaining_ms: 800000, last_client_seq: 4, current_turn: turn,
      }),
      'POST /student/sessions/:sid/answer': (() => {
        let attempts = 0
        return () => ++attempts === 1
          ? err('provider_unavailable', 503)
          : json({ client_seq: 5, replayed: false, status: 'in_progress', turn: { ...turn, idx: 3, text: 'Question 3' }, server_now: '', remaining_ms: 700000 })
      })(),
    })
    app(f)
    fireEvent.change(screen.getByLabelText('Viva ID'), { target: { value: 'v1' } })
    fireEvent.change(screen.getByLabelText('Student ID'), { target: { value: 'S1' } })
    fireEvent.change(screen.getByLabelText('Access code'), { target: { value: 'AAAA-1111' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    await screen.findByLabelText('Your answer')

    const answer = screen.getByLabelText('Your answer') as HTMLTextAreaElement
    fireEvent.change(answer, { target: { value: '  It maps keys to buckets.  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send answer' }))
    await screen.findByRole('alert')
    expect(answer.value).toBe('  It maps keys to buckets.  ')

    fireEvent.click(screen.getByRole('button', { name: 'Send answer' }))
    await screen.findAllByText('Question 3')
    const submissions = log.filter((line) => line.startsWith('POST /student/sessions/:sid/answer '))
    expect(submissions).toHaveLength(2)
    expect(JSON.parse(submissions[0].split(' ').slice(2).join(' '))).toEqual({ text: 'It maps keys to buckets.', client_seq: 5 })
    expect(JSON.parse(submissions[1].split(' ').slice(2).join(' '))).toEqual({ text: 'It maps keys to buckets.', client_seq: 5 })
  })
})
