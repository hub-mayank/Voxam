import { describe, expect, it } from 'vitest'
import { VoiceClient, type SocketLike } from './client'
import { pcm16ToBytes } from './pcm'

class FakeSocket implements SocketLike {
  binaryType = 'blob'
  readyState = 0
  sent: (string | ArrayBuffer)[] = []
  onopen: SocketLike['onopen'] = null
  onmessage: SocketLike['onmessage'] = null
  onclose: SocketLike['onclose'] = null
  onerror: SocketLike['onerror'] = null
  send(d: string | ArrayBuffer) { this.sent.push(d) }
  close(code = 1000) { this.readyState = 3; this.onclose?.({ code, wasClean: true }) }
  open() { this.readyState = 1; this.onopen?.({}) }
  push(msg: object) { this.onmessage?.({ data: JSON.stringify(msg) }) }
  pushBinary(buf: ArrayBuffer) { this.onmessage?.({ data: buf }) }
  json() { return this.sent.filter((s): s is string => typeof s === 'string').map((s) => JSON.parse(s)) }
}

function setup(mode: 'push_to_talk' | 'hands_free' = 'push_to_talk') {
  const socket = new FakeSocket()
  const seen: [string, unknown][] = []
  const events = new Proxy({}, { get: (_t, name: string) => (...a: unknown[]) => { seen.push([name, a.length === 1 ? a[0] : a]) } })
  const client = new VoiceClient({ url: 'ws://x/voice', token: 'st_1', mode, socketFactory: () => socket, events: events as never })
  client.connect()
  socket.open()
  return { socket, client, seen, names: () => seen.map((s) => s[0]) }
}

describe('VoiceClient', () => {
  it('sends hello first with protocol 1, the token and the mode', () => {
    const { socket } = setup('hands_free')
    expect(socket.json()[0]).toEqual({ type: 'hello', protocol: 1, token: 'st_1', mode: 'hands_free', resume: false })
    expect(socket.binaryType).toBe('arraybuffer')
  })

  it('pairs an audio header with the binary frame that follows it', () => {
    const { socket, seen } = setup()
    socket.push({ type: 'audio', turn_idx: 2, sample_rate: 22050, format: 'pcm_s16le', bytes: 6, last: true })
    socket.pushBinary(pcm16ToBytes(new Int16Array([1, 2, 3])))
    const audio = seen.find((s) => s[0] === 'onAudio')![1] as [Int16Array, number, number]
    expect(Array.from(audio[0])).toEqual([1, 2, 3])
    expect(audio.slice(1)).toEqual([22050, 2])
    socket.pushBinary(new ArrayBuffer(4)) // a stray binary frame without a header is dropped
    expect(seen.filter((s) => s[0] === 'onAudio')).toHaveLength(1)
  })

  it('push-to-talk sends audio only while the button is held and emits a local interrupt on press', () => {
    const { socket, client, names } = setup()
    client.sendAudio(new Int16Array(320))
    expect(socket.sent.filter((s) => typeof s !== 'string')).toHaveLength(0)
    client.pressToTalk()
    client.sendAudio(new Int16Array(320))
    client.release()
    client.sendAudio(new Int16Array(320))
    expect(socket.json().map((m) => m.type)).toEqual(['hello', 'ptt_start', 'ptt_end'])
    expect(socket.sent.filter((s) => typeof s !== 'string')).toHaveLength(1)
    expect(names()).toContain('onInterrupt')
  })

  it('hands-free streams audio continuously and honours mute', () => {
    const { socket, client } = setup('hands_free')
    client.sendAudio(new Int16Array(320))
    client.mute()
    client.sendAudio(new Int16Array(320))
    client.unmute()
    client.sendAudio(new Int16Array(320))
    expect(socket.sent.filter((s) => typeof s !== 'string')).toHaveLength(2)
    expect(socket.json().map((m) => m.type)).toEqual(['hello', 'mute', 'unmute'])
  })

  it('decodes the server messages into events', () => {
    const { socket, seen } = setup()
    socket.push({ type: 'ready', protocol: 1, session_id: 's', status: 'in_progress', remaining_ms: 5000, server_now: '', last_client_seq: 0, current_turn: null, max_answer_ms: 90000 })
    socket.push({ type: 'transcript', seq: 1, text: 'hello', confidence: 0.9, stt_ms: 300 })
    socket.push({ type: 'ai_turn', idx: 2, text: 'next', phase: 'warmup', ended: false, remaining_ms: 4000, latency_ms: 850 })
    socket.push({ type: 'error', code: 'no_speech', message: 'too short', retryable: true })
    socket.push({ type: 'something_new' }) // unknown types are ignored
    socket.onmessage?.({ data: '{broken' }) // so is garbage
    const get = (n: string) => seen.find((s) => s[0] === n)![1]
    expect(get('onTranscript')).toEqual({ seq: 1, text: 'hello', confidence: 0.9, sttMs: 300 })
    expect(get('onAiTurn')).toMatchObject({ idx: 2, remainingMs: 4000, latencyMs: 850 })
    expect(get('onError')).toEqual({ code: 'no_speech', message: 'too short', retryable: true })
    expect(seen.map((s) => s[0])).toEqual(['onOpen', 'onReady', 'onTranscript', 'onAiTurn', 'onError'])
  })

  it('reports the close code', () => {
    const { socket, seen } = setup()
    socket.close(4409)
    expect(seen.find((s) => s[0] === 'onClosed')![1]).toEqual({ code: 4409, clean: true })
  })

  it('sends typed answers trimmed and capped', () => {
    const { socket, client } = setup()
    client.sendText('   ')
    client.sendText('  hi there  ')
    expect(socket.json().at(-1)).toEqual({ type: 'text_answer', text: 'hi there' })
    expect(socket.json().filter((m) => m.type === 'text_answer')).toHaveLength(1)
  })
})

describe('speech language', () => {
  it('is sent in hello only when the student chose one', () => {
    const plain = setup()
    expect(plain.socket.json()[0]).not.toHaveProperty('language')
    const socket = new FakeSocket()
    const client = new VoiceClient({ url: 'ws://x/voice', token: 'st_1', mode: 'push_to_talk', language: 'auto', socketFactory: () => socket })
    client.connect()
    socket.open()
    expect(socket.json()[0]).toMatchObject({ type: 'hello', protocol: 1, language: 'auto' })
  })
})

