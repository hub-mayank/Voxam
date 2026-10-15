// What a student reads for each failure. The exact code is logged for support (StudentError) and never shown.
import { ApiError } from '../api/client'
import type { ErrorCode } from '../api/types'

const MESSAGES: Record<ErrorCode | 'network_error', string> = {
  unauthorized: 'Your session is no longer valid. Please sign in again with your ID and access code.',
  forbidden: 'This page is not available for your account. Please sign in again.',
  not_found: 'We could not find this viva. Check the viva ID and try again.',
  method_not_allowed: 'Something went wrong on our side. Please reload the page.',
  validation_error: 'Please check what you typed and try again.',
  invalid_upload: 'Something went wrong on our side. Please reload the page.',
  invalid_credentials: 'That ID or access code did not work. Check both and try again.',
  already_exists: 'Something went wrong on our side. Please reload the page.',
  invalid_state: 'That step is not available right now. We are checking where you are.',
  session_ended: 'Your viva is complete. You can safely close this page.',
  deadline_passed: 'Time is up. Your last answer was not saved. Your viva is now complete.',
  bad_client_seq: 'We need to resync this question before continuing.',
  rules_version_mismatch: 'The rules were updated. Please sign in again to read and accept them.',
  range_not_satisfiable: 'Something went wrong on our side. Please reload the page.',
  audio_not_available: 'Something went wrong on our side. Please reload the page.',
  results_not_released: 'Your result is not available yet.',
  rate_limited: 'Too many tries. Please wait a moment before trying again.',
  provider_unavailable: 'The interviewer is busy for a moment. Your answer is safe: please try again.',
  internal_error: 'Something went wrong on our side. Please try again. If it keeps happening, tell your invigilator.',
  network_error: 'Connection lost. Check your internet and try again. Your viva timer may keep running.',
}

export function studentMessage(error: ApiError): string {
  return MESSAGES[error.code]
}

/** The viva's own error codes from the voice server (docs/VOICE_PROTOCOL.md) have plain wording too. */
export function voiceMessage(message: string): string {
  return message || 'The voice connection had a problem. You can type your answer instead.'
}
