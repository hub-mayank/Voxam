// Microphone -> 16 kHz PCM16 frames of 20 ms, plus a 0..1 level for the meter.
import workletUrl from './capture.worklet.js?url'
import { Framer, floatToPcm16, resample, rms, TARGET_RATE } from './pcm'

export interface Capture {
  stop(): void
}

export interface CaptureOptions {
  onFrame: (frame: Int16Array) => void
  onLevel?: (level: number) => void
  stream?: MediaStream
}

export type MicFailure = 'denied' | 'no_device' | 'busy' | 'unsupported' | 'unknown'

export class MicError extends Error {
  constructor(public reason: MicFailure, message: string) {
    super(message)
  }
}

const MESSAGES: Record<MicFailure, string> = {
  denied: 'The browser blocked the microphone. Click the lock icon in the address bar, allow the microphone, then reload.',
  no_device: 'No microphone was found. Plug one in or choose one in your system sound settings, then try again.',
  busy: 'The microphone is being used by another app. Close it (for example a video call) and try again.',
  unsupported: 'This browser cannot record audio here. Use a current Chrome, Edge, Safari or Firefox on https or localhost.',
  unknown: 'The microphone could not be started. Reload the page and try again.',
}

export function classifyMicError(e: unknown): MicError {
  const name = e instanceof DOMException ? e.name : ''
  const reason: MicFailure =
    name === 'NotAllowedError' || name === 'SecurityError' ? 'denied'
    : name === 'NotFoundError' || name === 'OverconstrainedError' ? 'no_device'
    : name === 'NotReadableError' || name === 'AbortError' ? 'busy'
    : name === 'TypeError' ? 'unsupported'
    : 'unknown'
  return new MicError(reason, MESSAGES[reason])
}

export async function openMicrophone(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) throw new MicError('unsupported', MESSAGES.unsupported)
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
  } catch (e) {
    throw classifyMicError(e)
  }
}

export async function startCapture(opts: CaptureOptions): Promise<Capture> {
  const stream = opts.stream ?? (await openMicrophone())
  const ctx = new AudioContext()
  await ctx.audioWorklet.addModule(workletUrl)
  const source = ctx.createMediaStreamSource(stream)
  const node = new AudioWorkletNode(ctx, 'voxam-capture')
  const framer = new Framer(320)
  node.port.onmessage = (ev: MessageEvent<Float32Array>) => {
    const block = ev.data
    opts.onLevel?.(rms(block))
    const pcm = floatToPcm16(resample(block, ctx.sampleRate, TARGET_RATE))
    for (const frame of framer.push(pcm)) opts.onFrame(frame)
  }
  source.connect(node) // not connected to the speakers: no echo of our own voice
  return {
    stop() {
      node.port.onmessage = null
      source.disconnect()
      node.disconnect()
      stream.getTracks().forEach((t) => t.stop())
      void ctx.close()
    },
  }
}

/** Mic check screen: ask for the microphone and measure the level for `ms`; always releases the device. */
export async function checkMicrophone(ms = 1500): Promise<{ ok: true; peak: number } | { ok: false; reason: MicFailure; message: string }> {
  try {
    const stream = await openMicrophone()
    let peak = 0
    const cap = await startCapture({ stream, onFrame: () => undefined, onLevel: (l) => { peak = Math.max(peak, l) } })
    await new Promise((r) => setTimeout(r, ms))
    cap.stop()
    return { ok: true, peak }
  } catch (e) {
    const err = e instanceof MicError ? e : classifyMicError(e)
    return { ok: false, reason: err.reason, message: err.message }
  }
}
