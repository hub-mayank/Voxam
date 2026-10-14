import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import ExportRelease from './ExportRelease'

const mock = vi.hoisted(() => ({ api: { getViva: vi.fn(), setResultsVisible: vi.fn(), exportCsv: vi.fn() }, logout: vi.fn() }))
vi.mock('../api/useFacultyApi', () => ({ useFacultyApi: () => mock }))
const viva = { id: 'test-viva', title: 'Test viva', results_visible_to_students: false }

beforeEach(() => {
  vi.resetAllMocks()
  mock.api.getViva.mockResolvedValue(viva)
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Export and release', () => {
  it('waits for the saved value, and reads it again on a fresh mount', async () => {
    let confirm: (value: unknown) => void = () => {}
    mock.api.setResultsVisible.mockReturnValue(new Promise((resolve) => { confirm = resolve }))
    render(<ExportRelease vivaId="test-viva" />)
    const toggle = await screen.findByRole('checkbox', { name: 'Release results to students' }) as HTMLInputElement
    fireEvent.click(toggle)
    expect(toggle.checked).toBe(false)
    expect(screen.queryByText('Results released.')).toBeNull()
    await act(async () => confirm({ ...viva, results_visible_to_students: true }))
    expect(toggle.checked).toBe(true)
    expect(mock.api.setResultsVisible).toHaveBeenCalledWith('test-viva', true)
    cleanup()
    mock.api.getViva.mockResolvedValue({ ...viva, results_visible_to_students: true })
    render(<ExportRelease vivaId="test-viva" />)
    expect((await screen.findByRole('checkbox') as HTMLInputElement).checked).toBe(true)
  })

  it('does not change the confirmed toggle on failure and retries the same save', async () => {
    mock.api.setResultsVisible.mockRejectedValueOnce(new ApiError('internal_error', 'Save failed', 500)).mockResolvedValue({ ...viva, results_visible_to_students: true })
    render(<ExportRelease vivaId="test-viva" />)
    fireEvent.click(await screen.findByRole('checkbox'))
    await screen.findByText('Save failed')
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Retry export or release' }))
    await screen.findByText('Results released.')
    expect(mock.api.setResultsVisible).toHaveBeenCalledTimes(2)
  })

  it('downloads a CSV blob only after the typed API call succeeds', async () => {
    const makeUrl = vi.fn().mockReturnValue('blob:test-download')
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: makeUrl })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    let confirm: (value: string) => void = () => {}
    mock.api.exportCsv.mockReturnValue(new Promise((resolve) => { confirm = resolve }))
    render(<ExportRelease vivaId="test-viva" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Download CSV' }))
    expect(makeUrl).not.toHaveBeenCalled()
    await act(async () => confirm('student_id,effective_total\nTEST,80\n'))
    expect(mock.api.exportCsv).toHaveBeenCalledWith('test-viva')
    expect(makeUrl.mock.calls[0][0].type).toBe('text/csv;charset=utf-8')
    expect(click).toHaveBeenCalledOnce()
    expect(document.querySelector('a[download]')).toBeNull()
  })

  it('logs out on 401', async () => {
    mock.api.getViva.mockRejectedValue(new ApiError('unauthorized', 'Expired', 401))
    render(<ExportRelease vivaId="test-viva" />)
    await waitFor(() => expect(mock.logout).toHaveBeenCalledOnce())
  })
})
