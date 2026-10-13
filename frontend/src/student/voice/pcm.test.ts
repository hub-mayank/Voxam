import { describe, expect, it } from 'vitest'
import { bytesToPcm16, Framer, floatToPcm16, pcm16ToBytes, pcm16ToFloat, resample, rms } from './pcm'

describe('pcm helpers', () => {
  it('converts floats to PCM16 with clipping and back within one step', () => {
    const pcm = floatToPcm16(new Float32Array([0, 0.5, -0.5, 1, -1, 2, -2]))
    expect(Array.from(pcm)).toEqual([0, 16384, -16384, 32767, -32768, 32767, -32768])
    const back = pcm16ToFloat(pcm)
    expect(back[1]).toBeCloseTo(0.5, 3)
    expect(back[4]).toBeCloseTo(-1, 3)
  })

  it('resamples by the ratio and keeps a constant signal constant', () => {
    const input = new Float32Array(480).fill(0.25) // 10 ms at 48 kHz
    const out = resample(input, 48000, 16000)
    expect(out.length).toBe(160)
    expect(out.every((v) => Math.abs(v - 0.25) < 1e-6)).toBe(true)
    expect(resample(input, 16000, 16000)).toBe(input)
  })

  it('cuts a stream into exact 20 ms frames and keeps the remainder', () => {
    const f = new Framer(320)
    expect(f.push(new Int16Array(100))).toHaveLength(0)
    const frames = f.push(new Int16Array(560)) // 660 total: two frames, 20 left over
    expect(frames).toHaveLength(2)
    expect(frames.every((x) => x.length === 320)).toBe(true)
    expect(f.push(new Int16Array(300))).toHaveLength(1)
  })

  it('measures level and round-trips bytes little-endian', () => {
    expect(rms(new Float32Array([0.5, -0.5, 0.5, -0.5]))).toBeCloseTo(0.5)
    expect(rms(new Float32Array(0))).toBe(0)
    const samples = new Int16Array([1, -2, 300, -32768, 32767])
    const bytes = pcm16ToBytes(samples)
    expect(new Uint8Array(bytes).slice(0, 4)).toEqual(new Uint8Array([1, 0, 254, 255]))
    expect(Array.from(bytesToPcm16(bytes))).toEqual(Array.from(samples))
  })
})
