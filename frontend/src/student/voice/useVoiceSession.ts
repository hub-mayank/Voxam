// The browser voice session for one viva: microphone, WebSocket (docs/VOICE_PROTOCOL.md), playback and state in one hook.
//   const voice = useVoiceSession({ sessionId, token })
//   voice.connect()  (from a button click: the browser only allows audio after a user gesture)
//   hold-to-talk button:  onPointerDown={voice.pressToTalk}  onPointerUp={voice.release}
//   typing fallback:      voice.sendText('...')   (also used automatically when the microphone is unavailable)
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { API_URL } from '../../api/client'
import { startCapture, type Capture, type MicError } from './capture'
import { VoiceClient, type SocketFactory } from './client'
import { createPlayer, type Player } from './player'
import type { ServerState, VoiceMode } from './types'

export interface VoiceLine {
  role: 'student' | 'ai' | 'system'
  text: string
  confidence?: number | null
}

export type Connection = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

export interface VoiceDeps {
  socketFactory?: SocketFactory
  startCapture?: typeof startCapture
  createPlayer?: (onIdle?: () => void) => Player
}

export interface VoiceOptions {
  sessionId: string
  token: string
  mode?: VoiceMode
  deps?: VoiceDeps
}

export interface VoiceSession {
  connection: Connection
  /** what the server says it is doing: listening, thinking, speaking, ended */
  serverState: ServerState | null
  /** true while the AI audio is still playing on this device */
  aiSpeaking: boolean
  aiText: string
  transcript: VoiceLine[]
  /** highest accepted answer sequence reported by the voice server */
  lastClientSeq: number | null
  remainingMs: number | null
  warning: boolean
  /** microphone level 0..1 for a meter */
  level: number
  micError: MicError | null
  error: { code: string; message: string; retryable: boolean } | null
  ended: { status: string; text: string } | null
  /** student stopped speaking -> first AI audio, from the last turn */
  latencyMs: number | null
  connect: () => Promise<void>
  disconnect: () => void
  pressToTalk: () => void
  release: () => void
  endTurn: () => void
  sendText: (text: string) => void
  clearError: () => void
}

const NO_RETRY = new Set([1000, 4400, 4401, 4403, 4409])
const MAX_RETRIES = 3

export function useVoiceSession({ sessionId, token, mode = 'push_to_talk', deps = {} }: VoiceOptions): VoiceSession {
  const [connection, setConnection] = useState<Connection>('idle')
  const [serverState, setServerState] = useState<ServerState | null>(null)
  const [aiSpeaking, setAiSpeaking] = useState(false)
  const [aiText, setAiText] = useState('')
  const [transcript, setTranscript] = useState<VoiceLine[]>([])
  const [lastClientSeq, setLastClientSeq] = useState<number | null>(null)
  const [deadline, setDeadline] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [warning, setWarning] = useState(false)
  const [level, setLevel] = useState(0)
  const [micError, setMicError] = useState<MicError | null>(null)
  const [error, setError] = useState<VoiceSession['error']>(null)
  const [ended, setEnded] = useState<VoiceSession['ended']>(null)
  const [latencyMs, setLatencyMs] = useState<number | null>(null)

  const client = useRef<VoiceClient | null>(null)
  const player = useRef<Player | null>(null)
  const capture = useRef<Capture | null>(null)
  const retries = useRef(0)
  const wantOpen = useRef(false)
  const spoken = useRef(new Set<number>())

  const url = useMemo(() => `${API_URL.replace(/^http/, 'ws')}/student/sessions/${encodeURIComponent(sessionId)}/voice`, [sessionId])

  const open = useCallback((resume: boolean) => {
    const c = new VoiceClient({
      url, token, mode, socketFactory: deps.socketFactory,
      events: {
        onOpen: () => { setConnection('open'); retries.current = 0 },
        onReady: (m) => {
          if (m.remaining_ms !== null) setDeadline(Date.now() + m.remaining_ms)
          if (m.current_turn) setAiText(m.current_turn.text)
          setLastClientSeq((current) => Math.max(current ?? 0, m.last_client_seq))
        },
        onState: setServerState,
        onTranscript: (t) => {
          setLastClientSeq((current) => Math.max(current ?? 0, t.seq))
          setTranscript((l) => [...l, { role: 'student', text: t.text, confidence: t.confidence }])
        },
        onAiTurn: (t) => {
          setAiText(t.text)
          setDeadline(Date.now() + t.remainingMs)
          setLatencyMs(t.latencyMs)
          if (!spoken.current.has(t.idx)) { // a reconnect speaks the open question again: show it once
            spoken.current.add(t.idx)
            setTranscript((l) => [...l, { role: 'ai', text: t.text }])
          }
        },
        onAudio: (pcm, rate) => { setAiSpeaking(true); player.current?.enqueue(pcm, rate) },
        onInterrupt: () => { player.current?.clear(); setAiSpeaking(false) },
        onTimer: (ms) => setDeadline(Date.now() + ms),
        onWarning: () => setWarning(true),
        onPrompt: (text) => setTranscript((l) => [...l, { role: 'system', text }]),
        onEnded: (info) => { setEnded(info); setServerState('ended') },
        onError: setError,
        onClosed: ({ code }) => {
          client.current = null
          if (!wantOpen.current || NO_RETRY.has(code) || retries.current >= MAX_RETRIES) {
            setConnection('closed')
            return
          }
          retries.current += 1
          setConnection('reconnecting')
          setTimeout(() => { if (wantOpen.current) open(true) }, 1000 * 2 ** (retries.current - 1))
        },
      },
    })
    client.current = c
    c.connect(resume)
  }, [url, token, mode, deps.socketFactory])

  const connect = useCallback(async () => {
    if (client.current) return
    wantOpen.current = true
    setConnection('connecting')
    setError(null)
    player.current = (deps.createPlayer ?? createPlayer)(() => setAiSpeaking(false))
    try {
      capture.current = await (deps.startCapture ?? startCapture)({
        onFrame: (f) => client.current?.sendAudio(f),
        onLevel: setLevel,
      })
      setMicError(null)
    } catch (e) {
      setMicError(e as MicError) // typing still works: connect anyway
    }
    open(false)
  }, [open, deps.createPlayer, deps.startCapture])

  const disconnect = useCallback(() => {
    wantOpen.current = false
    client.current?.disconnect()
    capture.current?.stop()
    player.current?.close()
    client.current = capture.current = player.current = null
    setConnection('closed')
  }, [])

  useEffect(() => () => {
    wantOpen.current = false
    client.current?.disconnect()
    capture.current?.stop()
    player.current?.close()
  }, [])

  useEffect(() => {
    if (deadline === null || ended) return
    const id = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(id)
  }, [deadline, ended])

  return {
    connection, serverState, aiSpeaking, aiText, transcript, lastClientSeq, warning, level, micError, error, ended, latencyMs,
    remainingMs: deadline === null ? null : ended ? 0 : Math.max(0, deadline - now),
    connect, disconnect,
    pressToTalk: () => client.current?.pressToTalk(),
    release: () => client.current?.release(),
    endTurn: () => client.current?.endTurn(),
    sendText: (text) => client.current?.sendText(text),
    clearError: () => setError(null),
  }
}
