// The WebSocket side of docs/VOICE_PROTOCOL.md, with no React and no audio devices: a small class that is easy to test
// with a fake socket. It sends hello first, decodes every server message, and pairs each `audio` header with the binary frame
// that follows it.
import { bytesToPcm16 } from './pcm'
import type { AiTurnInfo, ClientMsg, ServerMsg, ServerState, VoiceMode } from './types'

export interface SocketLike {
  binaryType: string
  readyState: number
  send(data: string | ArrayBuffer): void
  close(code?: number): void
  onopen: ((ev: unknown) => void) | null
  onmessage: ((ev: { data: unknown }) => void) | null
  onclose: ((ev: { code: number; wasClean?: boolean }) => void) | null
  onerror: ((ev: unknown) => void) | null
}

export type SocketFactory = (url: string) => SocketLike

export interface VoiceEvents {
  onOpen(): void
  onReady(msg: Extract<ServerMsg, { type: 'ready' }>): void
  onState(state: ServerState): void
  onSpeechStart(): void
  onTranscript(line: { seq: number; text: string; confidence: number | null; sttMs: number }): void
  onAiTurn(turn: AiTurnInfo & { remainingMs: number; latencyMs: number | null }): void
  onAudio(pcm: Int16Array, sampleRate: number, turnIdx: number): void
  onAudioDone(turnIdx: number): void
  onInterrupt(): void
  onTimer(remainingMs: number): void
  onWarning(remainingMs: number): void
  onPrompt(text: string): void
  onEnded(info: { status: string; text: string }): void
  onError(err: { code: string; message: string; retryable: boolean }): void
  onClosed(info: { code: number; clean: boolean }): void
}

export interface VoiceClientOptions {
  url: string
  token: string
  mode?: VoiceMode
  socketFactory?: SocketFactory
  events?: Partial<VoiceEvents>
}

const OPEN = 1

export class VoiceClient {
  private socket: SocketLike | null = null
  private pendingAudio: Extract<ServerMsg, { type: 'audio' }> | null = null
  private pressing = false
  private muted = false
  readonly mode: VoiceMode

  constructor(private opts: VoiceClientOptions) {
    this.mode = opts.mode ?? 'push_to_talk'
  }

  get connected(): boolean {
    return this.socket?.readyState === OPEN
  }

  private emit<K extends keyof VoiceEvents>(name: K, ...args: Parameters<VoiceEvents[K]>) {
    const handler = this.opts.events?.[name] as ((...a: Parameters<VoiceEvents[K]>) => void) | undefined
    handler?.(...args)
  }

  connect(resume = false) {
    const factory: SocketFactory = this.opts.socketFactory ?? ((u) => new WebSocket(u) as unknown as SocketLike)
    const socket = factory(this.opts.url)
    socket.binaryType = 'arraybuffer'
    this.socket = socket
    this.pendingAudio = null
    this.pressing = false
    socket.onopen = () => {
      this.sendJson({ type: 'hello', protocol: 1, token: this.opts.token, mode: this.mode, resume })
      this.emit('onOpen')
    }
    socket.onmessage = (ev) => this.onMessage(ev.data)
    socket.onclose = (ev) => {
      if (this.socket === socket) this.socket = null
      this.emit('onClosed', { code: ev.code, clean: ev.wasClean ?? ev.code === 1000 })
    }
    socket.onerror = () => {
      // the close event that follows carries the code; nothing else to do here
    }
  }

  disconnect() {
    const s = this.socket
    this.socket = null
    s?.close(1000)
  }

  private sendJson(msg: ClientMsg) {
    if (this.socket?.readyState === OPEN) this.socket.send(JSON.stringify(msg))
  }

  private onMessage(data: unknown) {
    if (typeof data !== 'string') {
      const header = this.pendingAudio
      this.pendingAudio = null
      if (header && data instanceof ArrayBuffer) this.emit('onAudio', bytesToPcm16(data), header.sample_rate, header.turn_idx)
      return
    }
    let msg: ServerMsg
    try {
      msg = JSON.parse(data) as ServerMsg
    } catch {
      return
    }
    switch (msg.type) {
      case 'ready': return this.emit('onReady', msg)
      case 'state': return this.emit('onState', msg.state)
      case 'speech_start': return this.emit('onSpeechStart')
      case 'transcript': return this.emit('onTranscript', { seq: msg.seq, text: msg.text, confidence: msg.confidence, sttMs: msg.stt_ms })
      case 'ai_turn':
        return this.emit('onAiTurn', { idx: msg.idx, text: msg.text, phase: msg.phase, ended: msg.ended, remainingMs: msg.remaining_ms, latencyMs: msg.latency_ms })
      case 'audio': this.pendingAudio = msg; return
      case 'audio_done': return this.emit('onAudioDone', msg.turn_idx)
      case 'interrupt': return this.emit('onInterrupt')
      case 'timer': return this.emit('onTimer', msg.remaining_ms)
      case 'time_warning': return this.emit('onWarning', msg.remaining_ms)
      case 'silence_prompt': return this.emit('onPrompt', msg.text)
      case 'ended': return this.emit('onEnded', { status: msg.status, text: msg.text })
      case 'error': return this.emit('onError', { code: msg.code, message: msg.message, retryable: msg.retryable })
      default: return // unknown message types are ignored (protocol rule)
    }
  }

  // ---- what the student does ----

  /** Push-to-talk: the button went down. Speaking over the AI is allowed; the server answers with `interrupt`. */
  pressToTalk() {
    if (this.pressing) return
    this.pressing = true
    this.emit('onInterrupt') // stop our own playback at once, do not wait for the round trip
    this.sendJson({ type: 'ptt_start' })
  }

  /** Push-to-talk: the button went up. The server transcribes and answers. */
  release() {
    if (!this.pressing) return
    this.pressing = false
    this.sendJson({ type: 'ptt_end' })
  }

  /** Hands-free: "I'm done" without waiting for the silence. */
  endTurn() {
    this.sendJson({ type: 'end_turn' })
  }

  sendText(text: string) {
    const clean = text.trim()
    if (clean) this.sendJson({ type: 'text_answer', text: clean.slice(0, 4000) })
  }

  mute() {
    this.muted = true
    this.sendJson({ type: 'mute' })
  }

  unmute() {
    this.muted = false
    this.sendJson({ type: 'unmute' })
  }

  /** One 16 kHz PCM16 frame from the microphone. Push-to-talk sends only while the button is held. */
  sendAudio(frame: Int16Array) {
    if (!this.connected || this.muted) return
    if (this.mode === 'push_to_talk' && !this.pressing) return
    const copy = frame.slice().buffer as ArrayBuffer
    this.socket?.send(copy)
  }

  ping() {
    this.sendJson({ type: 'ping', t: Date.now() })
  }
}
