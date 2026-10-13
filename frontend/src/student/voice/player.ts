// Plays the AI's PCM chunks back to back and can drop everything at once (barge-in).
import { pcm16ToFloat } from './pcm'

export interface Player {
  enqueue(pcm: Int16Array, sampleRate: number): void
  /** stop now and forget everything queued */
  clear(): void
  /** true while queued audio is still playing */
  readonly playing: boolean
  close(): void
}

export function createPlayer(onIdle?: () => void): Player {
  const ctx = new AudioContext()
  let nextTime = 0
  const live = new Set<AudioBufferSourceNode>()
  return {
    enqueue(pcm, sampleRate) {
      if (pcm.length === 0) return
      void ctx.resume() // allowed because the student pressed a button before the first sound
      const buffer = ctx.createBuffer(1, pcm.length, sampleRate)
      buffer.getChannelData(0).set(pcm16ToFloat(pcm))
      const src = ctx.createBufferSource()
      src.buffer = buffer
      src.connect(ctx.destination)
      const start = Math.max(ctx.currentTime + 0.02, nextTime)
      src.start(start)
      nextTime = start + buffer.duration
      live.add(src)
      src.onended = () => {
        live.delete(src)
        if (live.size === 0) onIdle?.()
      }
    },
    clear() {
      for (const s of live) {
        s.onended = null
        try {
          s.stop()
        } catch {
          // already finished
        }
      }
      live.clear()
      nextTime = 0
    },
    get playing() {
      return live.size > 0
    },
    close() {
      this.clear()
      void ctx.close()
    },
  }
}
