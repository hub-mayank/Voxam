// One typed function per student endpoint (docs/API.md). The session token is the Authorization bearer.
import { request, type RequestOptions } from './client'
import type { AnswerResponse, ConsentResponse, JoinRequest, JoinResponse, StartResponse, StatusResponse, StudentResult } from './types'

export function studentApi(token: string | null, fetchImpl?: typeof fetch) {
  const o = (extra: Partial<RequestOptions> = {}): RequestOptions => ({ token, fetchImpl, ...extra })
  const s = (sid: string) => `/student/sessions/${encodeURIComponent(sid)}`
  return {
    join: (body: JoinRequest) => request<JoinResponse>('POST', '/student/join', { fetchImpl, json: body }),
    consent: (sid: string, rulesVersion: string, accepted = true) =>
      request<ConsentResponse>('POST', `${s(sid)}/consent`, o({ json: { accepted, rules_version: rulesVersion } })),
    start: (sid: string) => request<StartResponse>('POST', `${s(sid)}/start`, o()),
    answer: (sid: string, text: string, clientSeq: number) =>
      request<AnswerResponse>('POST', `${s(sid)}/answer`, o({ json: { text, client_seq: clientSeq } })),
    status: (sid: string) => request<StatusResponse>('GET', `${s(sid)}/status`, o()),
    result: (sid: string) => request<StudentResult>('GET', `${s(sid)}/result`, o()),
  }
}

export type StudentApi = ReturnType<typeof studentApi>
