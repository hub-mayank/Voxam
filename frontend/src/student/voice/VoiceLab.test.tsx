import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup } from '@testing-library/react'
import { StudentSessionProvider } from '../session/StudentSessionProvider'
import VoiceLab from './VoiceLab'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const turn = { idx: 0, text: 'Hi, welcome. Tell me about a project.', phase: 'warmup', ended: false }

function backend(opts: { wrongCode?: boolean } = {}) {
  const calls: string[] = []
  const f = (async (url: string, init: RequestInit) => {
    const path = new URL(String(url)).pathname.replace(/\/student\/sessions\/[^/]+/, '/student/sessions/:sid')
    calls.push(`${init.method} ${path}`)
    if (path === '/student/join') {
      if (opts.wrongCode) return json({ error: { code: 'invalid_credentials', message: 'That ID or code is not right.', details: {} } }, 403)
      return json({ session_id: 'sid1', session_token: 'st_t', status: 'created', resumed: false, viva_title: 'DSA viva', duration_ms: 900000,
        rules_text: 'This is a recorded viva.', rules_version: 'rules-v1' })
    }
    if (path.endsWith('/consent')) return json({ status: 'consented', consent_at: '' })
    if (path.endsWith('/start')) return json({ status: 'in_progress', started_at: '', deadline_at: '', server_now: '', remaining_ms: 900000, turn })
    return json({ error: { code: 'not_found', message: 'x', details: {} } }, 404)
  }) as unknown as typeof fetch
  return { f, calls }
}

function renderLab(f: typeof fetch, url = '/student/voice-lab') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <StudentSessionProvider fetchImpl={f}>
        <VoiceLab />
      </StudentSessionProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => sessionStorage.clear())
afterEach(cleanup)

const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })
const click = (name: string | RegExp) => fireEvent.click(screen.getByRole('button', { name }))

describe('VoiceLab join flow', () => {
  it('goes from the join form through the rules and the mode choice to the lab', async () => {
    const { f, calls } = backend()
    renderLab(f)
    expect((screen.getByLabelText('Viva ID') as HTMLInputElement).value).toBe('local-dsa')
    expect((screen.getByRole('button', { name: 'Join' }) as HTMLButtonElement).disabled).toBe(true)
    type('Student ID', 'LOCAL01')
    type('Access code', 'ABCD-1234')
    click('Join')
    await screen.findByText('This is a recorded viva.')
    click('I accept')
    fireEvent.click(await screen.findByLabelText(/Hands-free/))
    click('Start')
    await screen.findByRole('button', { name: 'Connect' })
    expect(screen.queryByRole('button', { name: "I'm done" })).not.toBeNull() // the hands-free control, not hold-to-talk
    expect(screen.queryByRole('button', { name: 'Hold to talk' })).toBeNull()
    expect(calls).toEqual(['POST /student/join', 'POST /student/sessions/:sid/consent', 'POST /student/sessions/:sid/start'])
  })

  it('shows the server message for a wrong code and stays on the form', async () => {
    const { f } = backend({ wrongCode: true })
    renderLab(f)
    type('Student ID', 'LOCAL01')
    type('Access code', 'nope')
    click('Join')
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('That ID or code is not right.')
    expect(screen.queryByRole('button', { name: 'Join' })).not.toBeNull()
  })

  it('still accepts a session in the URL and skips the form', async () => {
    const { f, calls } = backend()
    renderLab(f, '/student/voice-lab?sid=abc&token=st_x')
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Connect' })).not.toBeNull())
    expect(screen.queryByRole('button', { name: 'Hold to talk' })).not.toBeNull()
    expect(calls).toEqual([])
  })
})
