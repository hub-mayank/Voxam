import { describe, expect, it } from 'vitest'
import { ApiError, request } from './client'
import { facultyApi } from './faculty'

function fakeFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: { url: string; init: RequestInit }[] = []
  const f = (async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), init })
    return handler(String(url), init)
  }) as unknown as typeof fetch
  return { f, calls }
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('request', () => {
  it('sends the bearer token and a JSON body', async () => {
    const { f, calls } = fakeFetch(() => json({ ok: true }))
    await request('POST', '/x', { token: 'tok', json: { a: 1 }, fetchImpl: f })
    expect(calls[0].init.headers).toMatchObject({ Authorization: 'Bearer tok', 'Content-Type': 'application/json' })
    expect(calls[0].init.body).toBe('{"a":1}')
  })

  it('turns the API error body into an ApiError with code, message and details', async () => {
    const { f } = fakeFetch(() => json({ error: { code: 'rate_limited', message: 'Wait.', details: { retry_after_ms: 4000 } } }, 429))
    const err = (await request('POST', '/student/join', { fetchImpl: f }).catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ code: 'rate_limited', status: 429, message: 'Wait.' })
    expect(err.retryAfterMs).toBe(4000)
  })

  it('maps a dropped connection to network_error and a non-JSON failure to internal_error', async () => {
    const down = fakeFetch(() => { throw new TypeError('Failed to fetch') })
    expect(await request('GET', '/x', { fetchImpl: down.f }).catch((e) => e)).toMatchObject({ code: 'network_error', status: 0 })
    const proxy = fakeFetch(() => new Response('<html>bad gateway</html>', { status: 502, statusText: 'Bad Gateway' }))
    expect(await request('GET', '/x', { fetchImpl: proxy.f }).catch((e) => e)).toMatchObject({ code: 'internal_error', status: 502 })
  })

  it('leaves out empty query values and lets the browser set the multipart header', async () => {
    const { f, calls } = fakeFetch(() => json({}))
    await request('GET', '/q', { query: { a: 1, b: undefined, c: '', d: false }, fetchImpl: f })
    expect(calls[0].url).toContain('?a=1&d=false')
    const form = new FormData()
    form.append('file', new Blob(['x']), 'a.csv')
    await request('POST', '/up', { form, fetchImpl: f })
    expect(calls[1].init.headers).not.toHaveProperty('Content-Type')
  })
})

describe('facultyApi', () => {
  it('builds the documented URLs and bodies', async () => {
    const { f, calls } = fakeFetch(() => json({}))
    const api = facultyApi('tok', f)
    await api.listSessions('dsa 1', { status: 'scored', low_confidence: true, search: 'asha', limit: 20, cursor: null })
    expect(calls[0].url).toBe('http://localhost:8000/faculty/vivas/dsa%201/sessions?status=scored&low_confidence=true&search=asha&limit=20')
    await api.approveQuestions('v', ['c01'])
    expect(JSON.parse(String(calls[1].init.body))).toEqual({ question_ids: ['c01'] })
    await api.approveQuestions('v')
    expect(JSON.parse(String(calls[2].init.body))).toEqual({})
    await api.setResultsVisible('v', true)
    expect(calls[3]).toMatchObject({ init: { method: 'PATCH' } })
    expect(JSON.parse(String(calls[3].init.body))).toEqual({ results_visible_to_students: true })
  })
})
