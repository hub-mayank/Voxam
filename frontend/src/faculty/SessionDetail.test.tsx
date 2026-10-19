import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SessionDetail as Detail } from '../api/types'
import SessionDetail from './SessionDetail'

const mock = vi.hoisted(() => ({ api: { getSession: vi.fn() }, logout: vi.fn() }))
vi.mock('../api/useFacultyApi', () => ({ useFacultyApi: () => mock }))

const detail: Detail = {
  session_id: 'sid1', viva_id: 'v', student_id: 'S1', status: 'scored', low_confidence: false, needs_review: false, low_confidence_reasons: [],
  turns: [
    { idx: 0, role: 'ai', text: 'Tell me about a project.', phase: 'warmup', action: 'open' },
    { idx: 1, role: 'student', text: 'I built a chat app with websockets.', phase: 'warmup' },
    { idx: 2, role: 'ai', text: 'Why did you choose websockets?', phase: 'depth', action: 'cross_check', question_id: 'xcheck' },
  ],
  audio: { available: false }, overrides: [], reviews: [],
  integrity_events: [{ id: 1, kind: 'tab_hidden', t_ms: 65000, detail: { duration_ms: 9200 } }],
}

beforeEach(() => mock.api.getSession.mockResolvedValue(detail))
afterEach(() => { cleanup(); vi.resetAllMocks() })

function open() {
  return render(<MemoryRouter initialEntries={['/s/sid1']}><Routes><Route path="/s/:sid" element={<SessionDetail />} /></Routes></MemoryRouter>)
}

describe('session detail', () => {
  it('shows the signals section and marks only the cross-check turn', async () => {
    open()
    expect(await screen.findByRole('heading', { name: 'Signals to look at' })).toBeTruthy()
    expect(screen.getByText(/01:05 · Tab hidden, away 9 s/)).toBeTruthy()
    expect(screen.getAllByText('Cross-check')).toHaveLength(1)
    expect(screen.getByRole('heading', { name: /Turn 2 — ai/ }).textContent).toContain('Cross-check')
    expect(screen.getByRole('heading', { name: /Turn 0 — ai/ }).textContent).not.toContain('Cross-check')
  })
})
