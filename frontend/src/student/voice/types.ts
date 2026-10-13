// The WebSocket protocol of docs/VOICE_PROTOCOL.md (v1), as TypeScript types.
export type VoiceMode = 'push_to_talk' | 'hands_free'
export type ServerState = 'listening' | 'thinking' | 'speaking' | 'ended'

export interface AiTurnInfo {
  idx: number
  text: string
  phase: string
  ended: boolean
}

export type ClientMsg =
  | { type: 'hello'; protocol: 1; token: string; mode: VoiceMode; resume: boolean }
  | { type: 'ptt_start' }
  | { type: 'ptt_end' }
  | { type: 'end_turn' }
  | { type: 'text_answer'; text: string }
  | { type: 'mute' }
  | { type: 'unmute' }
  | { type: 'ping'; t: number }

export type ServerMsg =
  | { type: 'ready'; protocol: 1; session_id: string; status: string; remaining_ms: number | null; server_now: string
      last_client_seq: number; current_turn: AiTurnInfo | null; max_answer_ms: number }
  | { type: 'state'; state: ServerState }
  | { type: 'speech_start'; t_ms: number }
  | { type: 'endpoint'; t_ms: number; reason: 'silence' | 'ptt' | 'button' | 'cap' }
  | { type: 'transcript'; seq: number; text: string; confidence: number | null; stt_ms: number }
  | ({ type: 'ai_turn'; remaining_ms: number; latency_ms: number | null } & AiTurnInfo)
  | { type: 'audio'; turn_idx: number; sample_rate: number; format: 'pcm_s16le'; bytes: number; last: boolean }
  | { type: 'audio_done'; turn_idx: number }
  | { type: 'interrupt' }
  | { type: 'timer'; remaining_ms: number; server_now: string }
  | { type: 'time_warning'; remaining_ms: number }
  | { type: 'silence_prompt'; text: string }
  | { type: 'ended'; status: string; text: string }
  | { type: 'error'; code: string; message: string; retryable: boolean }
  | { type: 'pong'; t: number }
