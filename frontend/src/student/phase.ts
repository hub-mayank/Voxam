// Screen plumbing shared by the student screens: which path belongs to which phase, redirects, focus and countdowns.
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useSession } from './session/StudentSessionProvider'
import type { Phase } from './session/state'

export const PATH: Record<Phase, string> = {
  login: '/student',
  rules: '/student/rules',
  ready: '/student/ready',
  viva: '/student/viva',
  done: '/student/done',
}

export type AnswerMode = 'text' | 'push_to_talk' | 'hands_free'
/** the language a voice student will speak: English (default) or Hindi/Hinglish (the recogniser detects) */
export type SpeakLanguage = 'en' | 'auto'

export function langOf(value: string | null): SpeakLanguage {
  return value === 'auto' ? 'auto' : 'en'
}

export function modeOf(value: string | null): AnswerMode {
  return value === 'push_to_talk' || value === 'hands_free' ? value : 'text'
}

/** Sends the student to the screen that matches the server's state (after a join, a reload or the deadline). `here` is the phase
 * this screen shows. Waits while a saved session is still being re-read. The query string (chosen answer mode) is kept. */
export function useStage(here: Phase) {
  const session = useSession()
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  useEffect(() => {
    if (session.restoring || session.phase === here) return
    const target = PATH[session.phase]
    if (pathname !== target) navigate(target + search, { replace: true })
  }, [session.restoring, session.phase, here, pathname, search, navigate])
  return session
}

/** Moves keyboard and screen-reader focus to the page heading when a screen appears. */
export function useFocusHeading() {
  useEffect(() => {
    const h = document.querySelector('h1')
    if (h) {
      h.setAttribute('tabindex', '-1')
      h.focus()
    }
  }, [])
}

/** Whole seconds until `until` (epoch ms), 0 when over or when there is nothing to wait for. */
export function useSecondsLeft(until: number | null): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (until === null) return
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(id)
  }, [until])
  return until === null ? 0 : Math.max(0, Math.ceil((until - now) / 1000))
}

const MIC_KEY = 'voxam.student.mic'

export function micChecked(): boolean {
  try {
    return sessionStorage.getItem(MIC_KEY) === '1'
  } catch {
    return false
  }
}

export function setMicChecked(ok: boolean) {
  try {
    if (ok) sessionStorage.setItem(MIC_KEY, '1')
    else sessionStorage.removeItem(MIC_KEY)
  } catch {
    // storage blocked: the student simply checks again
  }
}

export function clock(ms: number | null): string {
  if (ms === null) return '–:––'
  const s = Math.ceil(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
