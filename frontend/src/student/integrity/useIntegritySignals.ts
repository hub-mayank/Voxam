import { useEffect } from 'react'
import { ApiError } from '../../api/client'
import { studentApi } from '../../api/student'
import type { IntegritySignal } from '../../api/types'
import { createTracker } from './tracker'

const RETRY_MS = 5000

// tells the server what the page noticed while the viva runs; never blocks the student and never shows an error
export function useIntegritySignals(sessionId: string | null, token: string | null) {
  useEffect(() => {
    if (!sessionId || !token) return
    const api = studentApi(token)
    const timers: number[] = []

    async function post(signal: IntegritySignal, retry: boolean) {
      try {
        await api.integrity(sessionId as string, [signal])
      } catch (e) {
        // only a lost connection or a server hiccup is worth one more try
        const temporary = e instanceof ApiError && (e.code === 'network_error' || e.status >= 500)
        if (retry && temporary) timers.push(window.setTimeout(() => void post(signal, false), RETRY_MS))
      }
    }

    const tracker = createTracker((signal) => void post(signal, true))
    const onVisibility = () => (document.visibilityState === 'hidden' ? tracker.hidden() : tracker.visible())
    const onPaste = (e: ClipboardEvent) => tracker.paste(e.clipboardData?.getData('text').length ?? 0)
    const onCopy = () => tracker.copy(window.getSelection()?.toString().length ?? 0)

    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('blur', tracker.blur)
    window.addEventListener('focus', tracker.focus)
    document.addEventListener('paste', onPaste)
    document.addEventListener('copy', onCopy)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('blur', tracker.blur)
      window.removeEventListener('focus', tracker.focus)
      document.removeEventListener('paste', onPaste)
      document.removeEventListener('copy', onCopy)
      timers.forEach((t) => window.clearTimeout(t))
    }
  }, [sessionId, token])
}
