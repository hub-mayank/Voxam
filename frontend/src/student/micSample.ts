// A few seconds of the student's own voice for the mic check, played back so they can confirm they are heard.
import { openMicrophone } from './voice'

export interface Sample {
  url: string
  stop: () => void
}

/** null when this browser has no MediaRecorder: the check then relies on the level meter only. */
export async function recordSample(ms = 3000): Promise<Sample | null> {
  if (typeof MediaRecorder === 'undefined') return null
  const stream = await openMicrophone()
  const recorder = new MediaRecorder(stream) // the browser picks a format it can also play: never label it ourselves
  const parts: Blob[] = []
  recorder.ondataavailable = (e) => {
    if (e.data.size) parts.push(e.data)
  }
  const done = new Promise<void>((resolve) => {
    recorder.onstop = () => resolve()
  })
  recorder.start()
  await new Promise((r) => setTimeout(r, ms))
  recorder.stop()
  await done
  stream.getTracks().forEach((t) => t.stop())
  const url = URL.createObjectURL(new Blob(parts, { type: recorder.mimeType || 'audio/webm' }))
  return { url, stop: () => URL.revokeObjectURL(url) }
}
