import { describe, expect, it, vi } from 'vitest'
import { studentApi } from '../api/student'

const result = {
  total: 82,
  overridden: false,
  dimensions: [{ key: 'conceptual', score: 4, weight: 30 }],
  feedback: [{ text: 'Good explanation.', evidence: [2] }],
}

describe('student result API', () => {
  it('fetches the authenticated result for the session and returns its typed payload', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify(result), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })) as unknown as typeof fetch

    await expect(studentApi('session-token', fetchImpl).result('sid / 1')).resolves.toEqual(result)
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringMatching(/\/student\/sessions\/sid%20%2F%201\/result$/),
      expect.objectContaining({ method: 'GET', headers: { Authorization: 'Bearer session-token' } }),
    )
  })

  it('preserves a server error code when the result is not released', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({
      error: { code: 'results_not_released', message: 'Not yet', details: {} },
    }), { status: 403, headers: { 'Content-Type': 'application/json' } })) as unknown as typeof fetch

    await expect(studentApi('session-token', fetchImpl).result('sid1')).rejects.toMatchObject({
      code: 'results_not_released',
      status: 403,
    })
  })
})
