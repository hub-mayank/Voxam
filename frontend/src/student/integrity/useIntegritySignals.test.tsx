import { cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/client'
import { useIntegritySignals } from './useIntegritySignals'

const mock = vi.hoisted(() => ({ integrity: vi.fn() }))
vi.mock('../../api/student', () => ({ studentApi: () => mock }))

function paste(text: string) {
  const e = new Event('paste') as ClipboardEvent
  Object.defineProperty(e, 'clipboardData', { value: { getData: () => text } })
  document.dispatchEvent(e)
}

beforeEach(() => {
  vi.useFakeTimers()
  mock.integrity.mockReset()
  mock.integrity.mockResolvedValue({ recorded: 1 })
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('useIntegritySignals', () => {
  it('reports a paste as a length, never the text', () => {
    renderHook(() => useIntegritySignals('sid1', 'st_abc'))
    paste('my secret answer')
    expect(mock.integrity).toHaveBeenCalledTimes(1)
    const [sid, events] = mock.integrity.mock.calls[0]
    expect(sid).toBe('sid1')
    expect(events).toEqual([{ kind: 'paste', chars: 16, client_id: expect.any(String) }])
    expect(JSON.stringify(mock.integrity.mock.calls)).not.toContain('secret')
  })

  it('does nothing without a session', () => {
    renderHook(() => useIntegritySignals(null, null))
    paste('x')
    expect(mock.integrity).not.toHaveBeenCalled()
  })

  it('retries once after a lost connection and then gives up quietly', async () => {
    mock.integrity.mockRejectedValue(new ApiError('network_error', 'offline', 0))
    renderHook(() => useIntegritySignals('sid1', 'st_abc'))
    paste('abc')
    await vi.advanceTimersByTimeAsync(0)
    expect(mock.integrity).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000)
    expect(mock.integrity).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(20000)
    expect(mock.integrity).toHaveBeenCalledTimes(2)
  })

  it('drops a signal the server rejects', async () => {
    mock.integrity.mockRejectedValue(new ApiError('unauthorized', 'no', 401))
    renderHook(() => useIntegritySignals('sid1', 'st_abc'))
    paste('abc')
    await vi.advanceTimersByTimeAsync(30000)
    expect(mock.integrity).toHaveBeenCalledTimes(1)
  })

  it('stops listening when the viva screen goes away', () => {
    const view = renderHook(() => useIntegritySignals('sid1', 'st_abc'))
    view.unmount()
    paste('abc')
    expect(mock.integrity).not.toHaveBeenCalled()
  })
})
