import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import type { ErrorCode } from '../api/types'
import { studentMessage } from './copy'

const CODES: (ErrorCode | 'network_error')[] = [
  'unauthorized', 'forbidden', 'not_found', 'method_not_allowed', 'validation_error', 'invalid_upload', 'invalid_credentials',
  'already_exists', 'invalid_state', 'session_ended', 'deadline_passed', 'bad_client_seq', 'rules_version_mismatch',
  'range_not_satisfiable', 'audio_not_available', 'results_not_released', 'rate_limited', 'provider_unavailable', 'internal_error',
  'network_error',
]

describe('student error copy', () => {
  it('has a sentence for every error code, and none shows a raw code or a stack trace', () => {
    for (const code of CODES) {
      const text = studentMessage(new ApiError(code, 'server text', 400))
      expect(text.length).toBeGreaterThan(10)
      expect(text).not.toContain(code)
      expect(text.toLowerCase()).not.toContain('exception')
    }
  })

  it('tells a student what to do next for the common cases', () => {
    expect(studentMessage(new ApiError('invalid_credentials', '', 403))).toMatch(/check both/i)
    expect(studentMessage(new ApiError('deadline_passed', '', 409))).toMatch(/not saved/i)
    expect(studentMessage(new ApiError('network_error', '', 0))).toMatch(/timer may keep running/i)
    expect(studentMessage(new ApiError('session_ended', '', 409))).toMatch(/safely close/i)
  })
})
