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

// The voice server's own codes (docs/VOICE_PROTOCOL.md section 7), in the same plain words. Unknown codes fall back to the server's text.
const VOICE_MESSAGES: Record<string, string> = {
  replaced: 'Another window or tab is now listening. This one has stopped. Go to the tab or window that is now listening.',
  stt_failed: 'We could not understand that answer. Please say it again.',
  no_speech: 'We did not hear anything. Please speak again, and keep close to the microphone.',
  bad_message: 'That message could not be sent. Please try again, or type your answer instead.',
  provider_unavailable: 'Voice is not available right now. You can type your answer instead.',
  unauthorized: 'Your session is no longer valid. Please sign in again with your ID and access code.',
  session_ended: 'Your viva is complete. You can safely close this page.',
}

export function voiceMessage(code: string, message: string): string {
  return VOICE_MESSAGES[code] ?? (message || 'The voice connection had a problem. You can type your answer instead.')
}
