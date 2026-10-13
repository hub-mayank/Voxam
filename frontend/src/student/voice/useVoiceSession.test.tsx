import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SocketLike } from './client'
import type { Player } from './player'
import { useVoiceSession } from './useVoiceSession'

class FakeSocket implements SocketLike {
  binaryType = ''
  readyState = 0
  sent: (string | ArrayBuffer)[] = []
  onopen: SocketLike['onopen'] = null
  onmessage: SocketLike['onmessage'] = null
  onclose: SocketLike['onclose'] = null
  onerror: SocketLike['onerror'] = null
  send(d: string | ArrayBuffer) { this.sent.push(d) }
  close(code = 1000) { this.readyState = 3; this.onclose?.({ code, wasClean: code === 1000 }) }
  open() { this.readyState = 1; this.onopen?.({}) }
  push(msg: object) { this.onmessage?.({ data: JSON.stringify(msg) }) }
}

function rig() {
  const sockets: FakeSocket[] = []
  const played: number[] = []
  let cleared = 0
  const player: Player = { enqueue: (p) => { played.push(p.length) }, clear: () => { cleared += 1 }, playing: false, close: () => undefined }
  let frameSink: ((f: Int16Array) => void) | null = null
  const deps = {
    socketFactory: () => { const s = new FakeSocket(); sockets.push(s); return s },
    createPlayer: () => player,
    startCapture: async (o: { onFrame: (f: Int16Array) => void }) => { frameSink = o.onFrame; return { stop: () => undefined } },
  }
  return { sockets, played, cleared: () => cleared, deps, frames: (f: Int16Array) => frameSink?.(f) }
}

describe('useVoiceSession', () => {
  it('connects, shows the opener, plays audio and sends push-to-talk audio', async () => {
    const r = rig()
    const { result } = renderHook(() => useVoiceSession({ sessionId: 'sid', token: 'st_1', deps: r.deps }))
    await act(() => result.current.connect())
    expect(result.current.connection).toBe('connecting')
    act(() => r.sockets[0].open())
    expect(result.current.connection).toBe('open')
    act(() => {
      r.sockets[0].push({ type: 'ready', protocol: 1, session_id: 'sid', status: 'in_progress', remaining_ms: 900000, server_now: '', last_client_seq: 0,
        current_turn: { idx: 0, text: 'Welcome.', phase: 'warmup', ended: false }, max_answer_ms: 90000 })
      r.sockets[0].push({ type: 'ai_turn', idx: 0, text: 'Welcome.', phase: 'warmup', ended: false, remaining_ms: 899000, latency_ms: null })
      r.sockets[0].push({ type: 'audio', turn_idx: 0, sample_rate: 22050, format: 'pcm_s16le', bytes: 4, last: true })
      r.sockets[0].onmessage?.({ data: new Int16Array([1, 2]).buffer })
      r.sockets[0].push({ type: 'state', state: 'listening' })
    })
    expect(result.current).toMatchObject({ aiText: 'Welcome.', serverState: 'listening' })
    expect(result.current.transcript).toEqual([{ role: 'ai', text: 'Welcome.' }])
    expect(result.current.remainingMs).toBeGreaterThan(890000)
    expect(r.played).toEqual([2])
    act(() => { result.current.pressToTalk(); r.frames(new Int16Array(320)); result.current.release() })
    const types = r.sockets[0].sent.map((s) => (typeof s === 'string' ? JSON.parse(s).type : 'audio'))
    expect(types).toEqual(['hello', 'ptt_start', 'audio', 'ptt_end'])
    expect(r.cleared()).toBe(1) // pressing cleared our own playback
  })

  it('keeps working by typing when the microphone is refused', async () => {
    const r = rig()
    r.deps.startCapture = async () => { throw Object.assign(new Error('x'), { reason: 'denied', message: 'blocked' }) }
    const { result } = renderHook(() => useVoiceSession({ sessionId: 'sid', token: 'st_1', deps: r.deps }))
    await act(() => result.current.connect())
    act(() => r.sockets[0].open())
    expect(result.current.micError).toMatchObject({ reason: 'denied' })
    act(() => result.current.sendText('typed answer'))
    expect(JSON.parse(r.sockets[0].sent.at(-1) as string)).toEqual({ type: 'text_answer', text: 'typed answer' })
  })

  it('reconnects with resume after an abnormal close, but not after being replaced', async () => {
    const r = rig()
    const { result } = renderHook(() => useVoiceSession({ sessionId: 'sid', token: 'st_1', deps: r.deps }))
    await act(() => result.current.connect())
    act(() => r.sockets[0].open())
    act(() => r.sockets[0].close(1006))
    expect(result.current.connection).toBe('reconnecting')
    await waitFor(() => expect(r.sockets).toHaveLength(2), { timeout: 3000 })
    act(() => r.sockets[1].open())
    expect(JSON.parse(r.sockets[1].sent[0] as string)).toMatchObject({ type: 'hello', resume: true })
    act(() => r.sockets[1].close(4409))
    expect(result.current.connection).toBe('closed')
    expect(r.sockets).toHaveLength(2)
  })

  it('shows the ended message and a zero clock', async () => {
    const r = rig()
    const { result } = renderHook(() => useVoiceSession({ sessionId: 'sid', token: 'st_1', deps: r.deps }))
    await act(() => result.current.connect())
    act(() => r.sockets[0].open())
    act(() => r.sockets[0].push({ type: 'timer', remaining_ms: 30000, server_now: '' }))
    expect(result.current.remainingMs).toBeGreaterThan(29000)
    act(() => r.sockets[0].push({ type: 'ended', status: 'ended', text: 'Thank you.' }))
    expect(result.current).toMatchObject({ ended: { status: 'ended', text: 'Thank you.' }, remainingMs: 0, serverState: 'ended' })
  })
})
