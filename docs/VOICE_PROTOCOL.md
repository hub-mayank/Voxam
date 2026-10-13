# Voice protocol (WebSocket), version 1

Contract between the browser voice client (Bhavesh, BH-3) and the voice server (Claude VOICE, T4). Frozen when BH-3 starts; later changes need a line in the changelog at the bottom and a message to Bhavesh. The HTTP API (`docs/openapi.json`) is unchanged: join, consent, start, status and result stay HTTP. Voice only replaces *how answers are sent and AI turns are heard*.

## 1. Overview
1. HTTP: `join` → `consent` → `start` (the clock starts; the response holds the first AI turn).
2. Open `ws://<host>/student/sessions/{sid}/voice` and send `hello` with the session token.
3. Per turn: the student speaks, the server transcribes and sends it to the engine (same code path as `POST .../answer`), then streams the AI turn as text plus audio.
4. At the end the server sends `ended`, closes the socket, and the HTTP `status` / `result` calls work as before.

The server owns the clock, the question flow and the end of the viva (D1). The client only captures audio, plays audio and shows state.

## 2. Connection
- URL: `/student/sessions/{sid}/voice`. `wss://` outside localhost (browsers allow the microphone only on https or localhost).
- Browsers cannot set headers on a WebSocket, so the token goes in the **first message** (`hello`), within 5 s, else close `4401`.
- One connection per session. A new one replaces the old: the old gets `error` `replaced` and close `4409`.
- All JSON messages are text frames with a `type` field. Audio is binary frames (section 5). Unknown `type`s are ignored by both sides.

## 3. Messages
### Client → server
| type | fields | when |
|---|---|---|
| `hello` | `protocol: 1`, `token`, `mode`: `push_to_talk` or `hands_free`, `resume`: bool | first message after connect; `resume: true` on reconnect asks the server to speak the open question again |
| *binary* | PCM16 mono 16 kHz little-endian, any frame size (a 20 ms worklet frame = 640 bytes) | hands-free: continuously after `ready`. Push-to-talk: only between `ptt_start` and `ptt_end` |
| `ptt_start` | | push-to-talk: button pressed. If the AI is speaking this is a barge-in: the server sends `interrupt` |
| `ptt_end` | | push-to-talk: button released; the server transcribes and answers |
| `end_turn` | | hands-free: "I'm done" button; ends the answer without waiting for the silence |
| `text_answer` | `text` (1-4000 chars) | microphone unavailable: answer by typing, same flow |
| `mute` / `unmute` | | hands-free: client stopped or resumed sending audio; the server does not count the silence as the student being gone |
| `ping` | `t` | optional keep-alive every 15 s; answered by `pong` |

### Server → client
| type | fields | meaning |
|---|---|---|
| `ready` | `protocol`, `session_id`, `status`, `remaining_ms`, `server_now`, `last_client_seq`, `current_turn`: `{idx,text,phase,ended}`, `max_answer_ms` | connection accepted; same facts as HTTP `status` |
| `state` | `state`: `listening`, `thinking`, `speaking`, `ended` | drives the UI: enable the mic only in `listening`. Sent on every change |
| `speech_start` | `t_ms` | the server heard the student begin (hands-free) |
| `endpoint` | `t_ms`, `reason`: `silence`, `ptt`, `button`, `cap` | the answer was cut here; `cap` = the 90 s answer limit |
| `transcript` | `seq`, `text`, `confidence` (0-1 or null), `stt_ms` | what we understood. Show it as the student's turn |
| `ai_turn` | `idx`, `text`, `phase`, `ended`, `remaining_ms`, `latency_ms` (null for the first turn) | the AI's next turn. Audio for it follows |
| `audio` | `turn_idx`, `sample_rate`, `format: "pcm_s16le"`, `bytes`, `last`: bool | header for the **next binary frame** (the audio chunk). Chunks arrive sentence by sentence |
| `audio_done` | `turn_idx` | all audio for this turn was sent. Client plays it out, then the mic opens |
| `interrupt` | | barge-in: stop playing and clear the playback queue now |
| `timer` | `remaining_ms`, `server_now` | every 5 s; re-sync the countdown from it |
| `time_warning` | `remaining_ms` (≈ 60000) | one minute left |
| `silence_prompt` | `text` | the student has been silent too long; a spoken `ai_turn`-style prompt follows (`audio` frames) |
| `ended` | `status`, `text` | the viva is over (time, or the closing turn). Server closes with `1000` after the audio |
| `error` | `code`, `message`, `retryable` | see section 7 |
| `pong` | `t` | |

## 4. Flows
**Push-to-talk (build this first)**
```
C: hello{mode:push_to_talk}        S: ready ; state{speaking} ; ai_turn ; audio+bin... ; audio_done ; state{listening}
C: ptt_start, bin, bin, ..., ptt_end
S: state{thinking} ; endpoint{ptt} ; transcript ; ai_turn ; state{speaking} ; audio+bin... ; audio_done ; state{listening}
... repeat ... ; ai_turn{ended:true} ; audio... ; ended ; close 1000
```
**Hands-free** (same, but no `ptt_*`): the client streams frames all the time; the server runs VAD, sends `speech_start` and `endpoint{silence}` (default 600 ms of silence ends the answer, configurable on the server). If the student speaks while the AI is talking, the server sends `interrupt` and listens.

**Silence:** after the AI finishes, 20 s without speech → `silence_prompt` once per question. Policy is on the server; the client does nothing.

**Typing fallback:** at any time send `text_answer`; the flow continues from `transcript` (with `confidence: null`).

## 5. Audio
- Client → server: PCM signed 16-bit little-endian, mono, **16 000 Hz**. Resample in the worklet if the context runs at 44.1/48 kHz. Echo cancellation and noise suppression on in `getUserMedia`.
- Server → client: one `audio` JSON then one binary message with that chunk, `pcm_s16le`, mono, `sample_rate` as stated (Piper alba is 22 050 Hz; do not assume). Queue chunks and play back to back; clear the queue on `interrupt`.
- Max answer length 90 s (`max_answer_ms` in `ready`); the server cuts at the cap.

## 6. Timing and recording
- The server records **both sides** into one stereo WAV per session, 16 kHz, 16-bit: **left channel = the student** (what arrives in binary frames), **right channel = the AI's voice** (what the server sent, resampled to 16 kHz). Both channels sit on one wall-clock timeline that starts at the session's `started_at`, so silences and gaps are real silence and a replay sounds like the conversation.
- It is written incrementally (at most ~1 s behind), so a crash keeps what was received. A reconnect continues the same file.
- For every answer the server stores `t_start_ms` / `t_end_ms` = milliseconds since `started_at`, i.e. offsets into that WAV. The dashboard seeks the recording by them (evidence replay). If the AI is interrupted, its channel keeps what was sent (the student may have heard less).
- Student `transcript.seq` is the HTTP `client_seq`: the server assigns it, so a reconnect can never duplicate an answer.
- `latency_ms` in `ai_turn` = student stopped speaking → first audio byte sent (the metric in the spike's end-to-end tests).

## 7. Errors and close codes
`error` is sent before closing when possible. `retryable: true` means the client may reconnect or try again.

| code | when | close | retryable |
|---|---|---|---|
| `unauthorized` | bad, missing or rotated token | 4401 | no |
| `forbidden` | token belongs to another session | 4403 | no |
| `replaced` | a newer connection took over | 4409 | no |
| `invalid_state` | session not `in_progress` (not started, or already ended) | 4400 | no |
| `session_ended` | the viva is over | 1000 | no |
| `stt_failed` | speech recognition failed for this answer; the server asks the student to repeat (`ai_turn` with a canned line) | none | yes |
| `no_speech` | an answer with nothing recognisable; asked to repeat | none | yes |
| `provider_unavailable` | the LLM chain is down; the engine falls back to a canned reply | none | yes |
| `bad_message` | invalid JSON, wrong audio format, `text_answer` too long | none | yes |

## 8. Reconnect
1. Network drop: reconnect with the same token and `hello{resume:true}`. The server rebuilds from the database (`ready.current_turn`, `remaining_ms`) and speaks the open question again. The clock never paused.
2. Page reload or rejoin: call HTTP `join` again (new token), then connect.
3. An answer that was being processed when the socket dropped is finished by the server (it is stored before any model runs); on reconnect the client sees it in `ready.last_client_seq` and the next `ai_turn`.

## 9. Stub mode (for frontend work without models)
Start the backend with `VOICE_PROVIDER=stub`: no STT or TTS models, same messages and timing shape.
- Transcript: `"[stub answer N] <a fixed technical sentence>"`, `confidence: 0.9`, `stt_ms` ≈ 300.
- AI audio: a quiet 220 Hz tone, duration `max(0.6 s, 0.055 s × words)`, at 22 050 Hz, in sentence chunks, so the playback queue and `interrupt` can be tested.
- Everything else (timer, endpointing in push-to-talk, errors, reconnect) is real. Hands-free VAD in stub mode ends the answer after 600 ms without level on the incoming frames.

## 10. TypeScript types (copy into `frontend/src/student/voice/types.ts`)
```ts
export type ClientMsg =
  | { type: 'hello'; protocol: 1; token: string; mode: 'push_to_talk' | 'hands_free'; resume: boolean }
  | { type: 'ptt_start' } | { type: 'ptt_end' } | { type: 'end_turn' }
  | { type: 'text_answer'; text: string } | { type: 'mute' } | { type: 'unmute' } | { type: 'ping'; t: number }

export type AiTurn = { idx: number; text: string; phase: string; ended: boolean }
export type ServerMsg =
  | { type: 'ready'; protocol: 1; session_id: string; status: string; remaining_ms: number; server_now: string
      last_client_seq: number; current_turn: AiTurn | null; max_answer_ms: number }
  | { type: 'state'; state: 'listening' | 'thinking' | 'speaking' | 'ended' }
  | { type: 'speech_start'; t_ms: number }
  | { type: 'endpoint'; t_ms: number; reason: 'silence' | 'ptt' | 'button' | 'cap' }
  | { type: 'transcript'; seq: number; text: string; confidence: number | null; stt_ms: number }
  | ({ type: 'ai_turn'; remaining_ms: number; latency_ms: number | null } & AiTurn)
  | { type: 'audio'; turn_idx: number; sample_rate: number; format: 'pcm_s16le'; bytes: number; last: boolean }
  | { type: 'audio_done'; turn_idx: number }
  | { type: 'interrupt' } | { type: 'timer'; remaining_ms: number; server_now: string }
  | { type: 'time_warning'; remaining_ms: number } | { type: 'silence_prompt'; text: string }
  | { type: 'ended'; status: string; text: string }
  | { type: 'error'; code: string; message: string; retryable: boolean } | { type: 'pong'; t: number }
```

## Changelog
- v1 (2026-10-13): first version.
- v1 (2026-10-13, same day): recording is stereo, student left and AI right, on one timeline (section 6). No client-visible change.
