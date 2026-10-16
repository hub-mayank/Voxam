import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import ExportRelease from './ExportRelease'

const mock = vi.hoisted(() => ({ api: { exportCsv: vi.fn() }, logout: vi.fn() }))
vi.mock('../api/useFacultyApi', () => ({ useFacultyApi: () => mock }))

const createObjectURLDescriptor = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
const revokeObjectURLDescriptor = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')

beforeEach(() => {
  vi.resetAllMocks()
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:test') })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})

afterEach(() => {
  cleanup()
  vi.clearAllTimers()
  vi.restoreAllMocks()
  if (createObjectURLDescriptor) Object.defineProperty(URL, 'createObjectURL', createObjectURLDescriptor)
  else Reflect.deleteProperty(URL, 'createObjectURL')
  if (revokeObjectURLDescriptor) Object.defineProperty(URL, 'revokeObjectURL', revokeObjectURLDescriptor)
  else Reflect.deleteProperty(URL, 'revokeObjectURL')
})

describe('faculty CSV export', () => {
  it('downloads the CSV returned by the existing faculty API', async () => {
    mock.api.exportCsv.mockResolvedValue('student_id,total\nTEST,87\n')
    const clickedLinks: HTMLAnchorElement[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clickedLinks.push(this)
    })
    render(<ExportRelease vivaId="test-viva" />)

    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }))

    expect((await screen.findByRole('status')).textContent).toBe('CSV download started.')
    expect(mock.api.exportCsv).toHaveBeenCalledWith('test-viva')
    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.objectContaining({ type: 'text/csv;charset=utf-8' }))
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce()
    expect(clickedLinks[0]?.download).toBe('viva-results.csv')
    expect(clickedLinks[0]?.href).toBe('blob:test')
  })

  it('shows export errors and allows retrying', async () => {
    mock.api.exportCsv
      .mockRejectedValueOnce(new ApiError('internal_error', 'Export failed', 500))
      .mockResolvedValueOnce('student_id,total\nTEST,87\n')
    render(<ExportRelease vivaId="test-viva" />)

    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Export failed')
    expect(mock.logout).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }))
    expect((await screen.findByRole('status')).textContent).toBe('CSV download started.')
    expect(mock.api.exportCsv).toHaveBeenCalledTimes(2)
  })
})
