// The only place that calls fetch. Every API function goes through request(), so auth headers, error shapes and
// network failures are handled once. The error body is {error: {code, message, details}} (docs/API.md).
import type { ErrorCode } from './types'

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    public code: ErrorCode | 'network_error',
    message: string,
    public status: number,
    public details: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'ApiError'
  }

  /** Milliseconds to wait before trying again, when the server said so (rate_limited, provider_unavailable). */
  get retryAfterMs(): number | null {
    const v = this.details.retry_after_ms
    return typeof v === 'number' ? v : null
  }
}

export interface RequestOptions {
  token?: string | null
  json?: unknown
  form?: FormData
  query?: Record<string, string | number | boolean | null | undefined>
  /** 'json' (default), 'text' or 'blob' */
  as?: 'json' | 'text' | 'blob'
  fetchImpl?: typeof fetch
  signal?: AbortSignal
}

function url(path: string, query?: RequestOptions['query']): string {
  const u = new URL(path, API_URL)
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== '') u.searchParams.set(k, String(v))
  }
  return u.toString()
}

export async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`
  let body: BodyInit | undefined
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.json)
  } else if (opts.form) {
    body = opts.form // the browser sets the multipart boundary
  }
  let res: Response
  try {
    res = await (opts.fetchImpl ?? fetch)(url(path, opts.query), { method, headers, body, signal: opts.signal })
  } catch (e) {
    throw new ApiError('network_error', e instanceof Error ? e.message : 'Network error', 0)
  }
  if (!res.ok) {
    let code: ErrorCode | 'network_error' = 'internal_error'
    let message = res.statusText || 'Request failed'
    let details: Record<string, unknown> = {}
    try {
      const data = await res.json()
      code = data.error?.code ?? code
      message = data.error?.message ?? message
      details = data.error?.details ?? {}
    } catch {
      // not our JSON error body (a proxy page, for instance): keep the defaults
    }
    throw new ApiError(code, message, res.status, details)
  }
  if (opts.as === 'text') return (await res.text()) as T
  if (opts.as === 'blob') return (await res.blob()) as T
  return (await res.json()) as T
}
