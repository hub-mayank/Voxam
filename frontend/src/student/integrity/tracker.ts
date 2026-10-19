import type { IntegritySignal } from '../../api/types'

// shorter than this is a notification or a click in the address bar, not worth a signal
export const MIN_AWAY_MS = 3000

// turns browser events into signals; only lengths ever leave the page, never the text
export function createTracker(send: (signal: IntegritySignal) => void, now: () => number = Date.now, newId: () => string = () => Math.random().toString(36).slice(2, 10)) {
  let hiddenAt: number | null = null
  let blurAt: number | null = null
  let hiddenDuringBlur = false

  return {
    hidden() {
      hiddenAt = now()
      if (blurAt !== null) hiddenDuringBlur = true
    },
    visible() {
      if (hiddenAt === null) return
      const duration = now() - hiddenAt
      hiddenAt = null
      if (duration >= MIN_AWAY_MS) send({ kind: 'tab_hidden', duration_ms: duration, client_id: newId() })
    },
    blur() {
      if (blurAt !== null) return
      blurAt = now()
      hiddenDuringBlur = hiddenAt !== null
    },
    focus() {
      if (blurAt === null) return
      const duration = now() - blurAt
      const sameAsTabSwitch = hiddenDuringBlur
      blurAt = null
      hiddenDuringBlur = false
      // switching tabs fires blur too, but that is already sent as tab_hidden
      if (!sameAsTabSwitch && duration >= MIN_AWAY_MS) send({ kind: 'window_blur', duration_ms: duration, client_id: newId() })
    },
    paste(chars: number) {
      send({ kind: 'paste', chars, client_id: newId() })
    },
    copy(chars: number) {
      if (chars > 0) send({ kind: 'copy', chars, client_id: newId() })
    },
  }
}
