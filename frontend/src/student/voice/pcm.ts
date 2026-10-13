// Pure audio helpers (no browser APIs), so they are unit-tested: float samples <-> PCM16, resampling, framing.
export const TARGET_RATE = 16_000

export function floatToPcm16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]))
    out[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff)
  }
  return out
}

export function pcm16ToFloat(input: Int16Array): Float32Array {
  const out = new Float32Array(input.length)
  for (let i = 0; i < input.length; i++) out[i] = input[i] / (input[i] < 0 ? 0x8000 : 0x7fff)
  return out
}

/** Linear-interpolation resampler (speech recognition input; quality is enough for 16 kHz speech). */
export function resample(input: Float32Array, fromRate: number, toRate: number = TARGET_RATE): Float32Array {
  if (fromRate === toRate || input.length === 0) return input
  const outLength = Math.floor((input.length * toRate) / fromRate)
  const out = new Float32Array(outLength)
  const ratio = fromRate / toRate
  for (let i = 0; i < outLength; i++) {
    const pos = i * ratio
    const j = Math.floor(pos)
    const frac = pos - j
    out[i] = j + 1 < input.length ? input[j] * (1 - frac) + input[j + 1] * frac : input[input.length - 1]
  }
  return out
}

/** Collects samples and hands out fixed-size frames (20 ms = 320 samples at 16 kHz). */
export class Framer {
  private buf = new Int16Array(0)
  constructor(private frameSize: number = 320) {}

  push(samples: Int16Array): Int16Array[] {
    const merged = new Int16Array(this.buf.length + samples.length)
    merged.set(this.buf)
    merged.set(samples, this.buf.length)
    const frames: Int16Array[] = []
    let offset = 0
    while (merged.length - offset >= this.frameSize) {
      frames.push(merged.slice(offset, offset + this.frameSize))
      offset += this.frameSize
    }
    this.buf = merged.slice(offset)
    return frames
  }
}

/** Root-mean-square level of float samples, 0..1, for the level meter. */
export function rms(samples: Float32Array): number {
  if (samples.length === 0) return 0
  let sum = 0
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i]
  return Math.sqrt(sum / samples.length)
}

/** Bytes of a binary WebSocket message -> Int16 samples (little-endian, as the server sends). */
export function bytesToPcm16(buf: ArrayBuffer): Int16Array {
  const view = new DataView(buf)
  const out = new Int16Array(Math.floor(buf.byteLength / 2))
  for (let i = 0; i < out.length; i++) out[i] = view.getInt16(i * 2, true)
  return out
}

export function pcm16ToBytes(samples: Int16Array): ArrayBuffer {
  const buf = new ArrayBuffer(samples.length * 2)
  const view = new DataView(buf)
  for (let i = 0; i < samples.length; i++) view.setInt16(i * 2, samples[i], true)
  return buf
}
