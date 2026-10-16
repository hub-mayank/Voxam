import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import BankUpload from './BankUpload'
import RosterUpload from './RosterUpload'
const mock = vi.hoisted(() => ({
  api: { listQuestions: vi.fn(), uploadQuestions: vi.fn(), generateQuestions: vi.fn(), approveQuestions: vi.fn(), listRoster: vi.fn(), uploadRoster: vi.fn(),
    resetCode: vi.fn(), revokeCode: vi.fn() },
  logout: vi.fn(),
}))
vi.mock('../api/useFacultyApi', () => ({ useFacultyApi: () => mock }))
const emptyBank = { items: [], warnings: [], concept_count: 0, applied_count: 0 }
const draft = { id: 'test-question', topic: 'test', text: 'Example question', key_points: [], source: 'ai-draft', difficulty: 1, type: 'concept' }
const rowError = () => new ApiError('invalid_upload', 'Upload rejected', 422, {
  rows: [{ row: 1, field: 'id', message: 'First row problem' }, { row: 3, field: 'name', message: 'Third row problem' }],
})
beforeEach(() => {
  vi.resetAllMocks()
  mock.api.listQuestions.mockResolvedValue(emptyBank)
  mock.api.listRoster.mockResolvedValue({ items: [] })
})
afterEach(() => { cleanup() })
describe('Faculty uploads', () => {
  it('lists every bank row error and retries the failed upload', async () => {
    mock.api.uploadQuestions.mockRejectedValueOnce(rowError()).mockResolvedValueOnce(emptyBank)
    render(<BankUpload vivaId="test-viva" />)
    await screen.findByText('No questions uploaded.')
    const file = new File(['[]'], 'bank.json', { type: 'application/json' })
    fireEvent.change(screen.getByLabelText('Question bank file (.json or .csv)'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload bank' }))
    await screen.findByText('Row 1, id: First row problem')
    expect(screen.getByText('Row 3, name: Third row problem')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry bank request' }))
    await screen.findByText('Question bank saved.')
    expect(mock.api.uploadQuestions).toHaveBeenLastCalledWith('test-viva', file)
  })
  it('does not claim approval until the server confirms it', async () => {
    mock.api.listQuestions.mockResolvedValue({ ...emptyBank, items: [draft] })
    let confirm: (value: unknown) => void = () => {}
    mock.api.approveQuestions.mockReturnValue(new Promise((resolve) => { confirm = resolve }))
    render(<BankUpload vivaId="test-viva" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Approve test-question' }))
    expect(screen.queryByText('Question approved.')).toBeNull()
    await act(async () => confirm({ ...emptyBank, items: [{ ...draft, source: 'bank', approved_by: 'test-reviewer' }] }))
    expect(screen.getByText('Question approved.')).toBeTruthy()
    expect(mock.api.approveQuestions).toHaveBeenCalledWith('test-viva', ['test-question'])
  })
  it('generates syllabus-based draft questions and keeps them unapproved until faculty approval', async () => {
    const generated = { ...draft, id: 'gen-123', source: 'ai-draft' }
    mock.api.generateQuestions.mockResolvedValue({ ...emptyBank, items: [generated] })
    mock.api.approveQuestions.mockResolvedValue({ ...emptyBank, items: [{ ...generated, source: 'bank', approved_by: 'dr-rao' }] })
    render(<BankUpload vivaId="test-viva" />)
    await screen.findByText('No questions uploaded.')
    fireEvent.change(screen.getByLabelText(/Generate drafts from syllabus/), { target: { value: 'Arrays and hash tables' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate draft questions' }))
    await screen.findByText('AI drafts added. Review each question and approve it before use.')
    expect(mock.api.generateQuestions).toHaveBeenCalledWith('test-viva', { syllabus: 'Arrays and hash tables', count: 10 })
    expect(screen.getByText('ai-draft')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Approve gen-123' }))
    await waitFor(() => expect(mock.api.approveQuestions).toHaveBeenCalledWith('test-viva', ['gen-123']))
  })
  it('lists every roster row error', async () => {
    mock.api.uploadRoster.mockRejectedValue(rowError())
    render(<RosterUpload vivaId="test-viva" />)
    await screen.findByText('No students uploaded.')
    fireEvent.change(screen.getByLabelText('Roster CSV (student_id,name)'), { target: { files: [new File(['student_id,name'], 'roster.csv')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload roster' }))
    await screen.findByText('Row 1, id: First row problem')
    expect(screen.getByText('Row 3, name: Third row problem')).toBeTruthy()
  })
  it('retains issued codes when the roster refresh fails, retries only the read, and clears codes on dismissal', async () => {
    // Synthetic value generated at runtime, never a real access code.
    const synthetic = crypto.randomUUID()
    const copy = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: copy } })
    mock.api.listRoster.mockResolvedValueOnce({ items: [] }).mockRejectedValueOnce(new ApiError('network_error', 'Refresh failed', 0)).mockResolvedValue({ items: [] })
    mock.api.uploadRoster.mockResolvedValue({ created: 1, unchanged: 0, items: [{ student_id: 'TEST', outcome: 'created', access_code: synthetic }] })
    render(<RosterUpload vivaId="test-viva" />)
    await screen.findByText('No students uploaded.')
    fireEvent.change(screen.getByLabelText('Roster CSV (student_id,name)'), { target: { files: [new File(['student_id,name'], 'roster.csv')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload roster' }))
    await screen.findByText('Refresh failed')
    fireEvent.click(screen.getByRole('button', { name: 'Copy code for TEST' }))
    await screen.findByText('Code copied.')
    expect(copy).toHaveBeenCalledWith(synthetic)
    fireEvent.click(screen.getByRole('button', { name: 'Retry roster request' }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(mock.api.uploadRoster).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss codes' }))
    expect(screen.queryByRole('button', { name: 'Copy code for TEST' })).toBeNull()
    cleanup()
    render(<RosterUpload vivaId="test-viva" />)
    await screen.findByText('No students uploaded.')
    expect(screen.queryByText('Newly issued access codes')).toBeNull()
  })
  it('logs out on a rejected saved token', async () => {
    mock.api.listQuestions.mockRejectedValue(new ApiError('unauthorized', 'Expired', 401))
    render(<BankUpload vivaId="test-viva" />)
    await waitFor(() => expect(mock.logout).toHaveBeenCalledOnce())
  })

  it('issues a new code once, says the old one stops working, and can revoke a code', async () => {
    const entry = { student_id: 'S1', name: 'Asha', session_id: null, session_status: null, access_code_active: true }
    mock.api.listRoster.mockResolvedValue({ items: [entry] })
    mock.api.resetCode.mockResolvedValue({ student_id: 'S1', access_code: 'H4TN-6WZB', issued_at: '2026-10-15T10:00:00Z' })
    mock.api.revokeCode.mockResolvedValue({ ...entry, access_code_active: false })
    render(<RosterUpload vivaId="test-viva" />)
    await screen.findByText(/S1 Asha/)
    fireEvent.click(screen.getByRole('button', { name: 'Issue new access code for S1' }))
    await screen.findByText('H4TN-6WZB')
    expect(screen.getByText(/previous code no longer works/i)).toBeTruthy()
    expect(mock.api.resetCode).toHaveBeenCalledWith('test-viva', 'S1')
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss code' }))
    expect(screen.queryByText('H4TN-6WZB')).toBeNull()
    fireEvent.click(await screen.findByRole('button', { name: 'Revoke access code for S1' }))
    await waitFor(() => expect(mock.api.revokeCode).toHaveBeenCalledWith('test-viva', 'S1'))
  })
})

