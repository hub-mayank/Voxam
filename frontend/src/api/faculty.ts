// One typed function per faculty endpoint (docs/API.md). Screens call these through useFacultyApi(), never fetch directly.
import { request, type RequestOptions } from './client'
import type {
  OverrideRequest, OverrideResult, QuestionList, RescoreResult, ResetCodeResult, ReviewRequest, ReviewResult, RosterList,
  RosterUploadResult, SessionDetail, SessionList, SessionStatus, Viva, VivaList,
} from './types'

export interface SessionFilters {
  status?: SessionStatus
  low_confidence?: boolean
  search?: string
  limit?: number
  cursor?: string | null
}

export function facultyApi(token: string, fetchImpl?: typeof fetch) {
  const o = (extra: Partial<RequestOptions> = {}): RequestOptions => ({ token, fetchImpl, ...extra })
  const v = (id: string) => `/faculty/vivas/${encodeURIComponent(id)}`
  const s = (id: string) => `/faculty/sessions/${encodeURIComponent(id)}`
  return {
    listVivas: () => request<VivaList>('GET', '/faculty/vivas', o()),
    getViva: (vivaId: string) => request<Viva>('GET', v(vivaId), o()),
    setResultsVisible: (vivaId: string, visible: boolean) =>
      request<Viva>('PATCH', v(vivaId), o({ json: { results_visible_to_students: visible } })),
    listQuestions: (vivaId: string) => request<QuestionList>('GET', `${v(vivaId)}/questions`, o()),
    uploadQuestions: (vivaId: string, file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<QuestionList>('POST', `${v(vivaId)}/questions`, o({ form }))
    },
    /** questionIds omitted: approve every ai-draft. */
    approveQuestions: (vivaId: string, questionIds?: string[]) =>
      request<QuestionList>('POST', `${v(vivaId)}/questions/approve`, o({ json: questionIds ? { question_ids: questionIds } : {} })),
    listRoster: (vivaId: string) => request<RosterList>('GET', `${v(vivaId)}/roster`, o()),
    uploadRoster: (vivaId: string, file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<RosterUploadResult>('POST', `${v(vivaId)}/roster`, o({ form }))
    },
    resetCode: (vivaId: string, studentId: string) =>
      request<ResetCodeResult>('POST', `${v(vivaId)}/roster/${encodeURIComponent(studentId)}/reset-code`, o()),
    listSessions: (vivaId: string, f: SessionFilters = {}) =>
      request<SessionList>('GET', `${v(vivaId)}/sessions`, o({ query: { ...f } })),
    getSession: (sid: string) => request<SessionDetail>('GET', s(sid), o()),
    override: (sid: string, body: OverrideRequest) => request<OverrideResult>('POST', `${s(sid)}/override`, o({ json: body })),
    review: (sid: string, body: ReviewRequest) => request<ReviewResult>('POST', `${s(sid)}/review`, o({ json: body })),
    rescore: (sid: string) => request<RescoreResult>('POST', `${s(sid)}/rescore`, o()),
    exportCsv: (vivaId: string) => request<string>('GET', `${v(vivaId)}/export.csv`, o({ as: 'text' })),
  }
}

export type FacultyApi = ReturnType<typeof facultyApi>
