import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { SessionDetail } from '../api/types'
import ReviewActions from './ReviewActions'

const mock = vi.hoisted(() => ({ api: { override: vi.fn(), review: vi.fn(), rescore: vi.fn(), getSession: vi.fn() }, logout: vi.fn() }))
vi.mock('../api/useFacultyApi', () => ({ useFacultyApi: () => mock }))
const detail: SessionDetail = {
  session_id: 'test-session', viva_id: 'test-viva', student_id: 'TEST', status: 'scored', turns: [],
  low_confidence: true, needs_review: true, low_confidence_reasons: [], audio: { available: false },
  overrides: [], reviews: [], integrity_events: [],
}
const fillOverride = (total = '80', reason = 'Checked the transcript') => {
  fireEvent.change(screen.getByLabelText('New total (0–100)'), { target: { value: total } })
  fireEvent.change(screen.getByLabelText('Override reason'), { target: { value: reason } })
  fireEvent.click(screen.getByRole('button', { name: 'Save override' }))
}
beforeEach(() => {
  vi.resetAllMocks()
  mock.api.getSession.mockResolvedValue(detail)
})
afterEach(() => { cleanup() })

describe('Faculty review actions', () => {
  it('rejects missing/out-of-range totals and invalid reasons without sending a request', () => {
    render(<ReviewActions detail={detail} onReload={() => {}} />)
    for (const total of ['', '-1', '101']) fillOverride(total)
    for (const reason of ['', '  ', 'ab', 'x'.repeat(2001)]) fillOverride('80', reason)
    expect(mock.api.override).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toBeTruthy()
  })

  it.each([0, 100])('accepts boundary score %s only after confirmation and reloads', async (value) => {
    let confirm: (result: unknown) => void = () => {}
    mock.api.override.mockReturnValue(new Promise((resolve) => { confirm = resolve }))
    const onReload = vi.fn()
    render(<ReviewActions detail={detail} onReload={onReload} />)
    fillOverride(String(value))
    expect(screen.queryByText(/Override saved/)).toBeNull()
    expect(mock.api.getSession).not.toHaveBeenCalled()
    await act(async () => confirm({ effective_total: value }))
    await waitFor(() => expect(onReload).toHaveBeenCalledWith(detail))
    expect(mock.api.override).toHaveBeenCalledWith('test-session', { new_total: value, reason: 'Checked the transcript' })
    expect(screen.getByText(`Override saved. Effective total: ${value} / 100.`)).toBeTruthy()
  })

  it('retries only the GET when an already-saved override cannot refresh', async () => {
    mock.api.override.mockResolvedValue({ effective_total: 80 })
    mock.api.getSession.mockRejectedValueOnce(new ApiError('network_error', 'Reload failed', 0)).mockResolvedValue(detail)
    render(<ReviewActions detail={detail} onReload={() => {}} />)
    fillOverride()
    fireEvent.click(await screen.findByRole('button', { name: 'Retry session refresh' }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(mock.api.override).toHaveBeenCalledOnce()
    expect(mock.api.getSession).toHaveBeenCalledTimes(2)
  })

  it('validates notes, saves a trimmed note, and renders server history', async () => {
    mock.api.review.mockResolvedValue({ needs_review: false })
    const history = { ...detail, reviews: [{ id: 1, note: 'Read transcript', reviewer: 'test-reviewer', at: '2026-10-14T00:00:00Z' }], overrides: [{ id: 2, old_total: 0, new_total: 80, reason: 'Reason from server', reviewer: 'test-reviewer', at: '2026-10-14T00:00:00Z' }] }
    mock.api.getSession.mockResolvedValue(history)
    const onReload = vi.fn()
    const view = render(<ReviewActions detail={detail} onReload={onReload} />)
    for (const note of ['', 'ab', 'x'.repeat(2001)]) {
      fireEvent.change(screen.getByLabelText('What was checked'), { target: { value: note } })
      fireEvent.click(screen.getByRole('button', { name: 'Save review note' }))
    }
    expect(mock.api.review).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('What was checked'), { target: { value: '  Read transcript  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save review note' }))
    await waitFor(() => expect(onReload).toHaveBeenCalledWith(history))
    expect(mock.api.review).toHaveBeenCalledWith('test-session', { note: 'Read transcript' })
    view.rerender(<ReviewActions detail={history} onReload={onReload} />)
    expect(screen.getByText(/0 → 80: Reason from server/)).toBeTruthy()
    expect(screen.getByText(/Read transcript — test-reviewer/)).toBeTruthy()
  })

  it('requires confirmation before queuing a rescore and reloads the session', async () => {
    mock.api.rescore.mockResolvedValue({ session_id: 'test-session', status: 'ended', job_status: 'queued' })
    const onReload = vi.fn()
    render(<ReviewActions detail={detail} onReload={onReload} />)
    fireEvent.click(screen.getByRole('button', { name: 'Request rescore' }))
    expect(mock.api.rescore).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(mock.api.rescore).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Request rescore' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm rescore' }))
    await waitFor(() => expect(onReload).toHaveBeenCalledWith(detail))
    expect(screen.getByText(/Rescoring request confirmed: queued/)).toBeTruthy()
  })

  it('shows errors without success, retries actions, and logs out on 401', async () => {
    mock.api.override.mockRejectedValueOnce(new ApiError('internal_error', 'Save failed', 500)).mockRejectedValueOnce(new ApiError('unauthorized', 'Expired', 401))
    render(<ReviewActions detail={detail} onReload={() => {}} />)
    fillOverride()
    fireEvent.click(await screen.findByRole('button', { name: 'Retry action' }))
    await waitFor(() => expect(mock.logout).toHaveBeenCalledOnce())
    expect(screen.queryByText(/Override saved/)).toBeNull()
  })

  it('disables actions for ineligible sessions', () => {
    render(<ReviewActions detail={{ ...detail, status: 'in_progress' }} onReload={() => {}} />)
    expect((screen.getByRole('button', { name: 'Request rescore' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('No overrides recorded.')).toBeTruthy()
    expect(screen.getByText('No review notes recorded.')).toBeTruthy()
  })
})
