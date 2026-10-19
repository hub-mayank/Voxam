import { describe, expect, it } from 'vitest'
import type { IntegritySignal } from '../../api/types'
import { createTracker, MIN_AWAY_MS } from './tracker'

function setup() {
  const sent: IntegritySignal[] = []
  let t = 1000
  let n = 0
  const tracker = createTracker((s) => sent.push(s), () => t, () => `id${++n}`)
  const wait = (ms: number) => { t += ms }
  return { sent, tracker, wait }
}

describe('integrity tracker', () => {
  it('sends nothing for a short absence', () => {
    const { sent, tracker, wait } = setup()
    tracker.hidden()
    wait(MIN_AWAY_MS - 1)
    tracker.visible()
    expect(sent).toEqual([])
  })

  it('sends one tab_hidden for a tab switch and not a window_blur, whichever event comes first', () => {
    for (const blurFirst of [true, false]) {
      const { sent, tracker, wait } = setup()
      if (blurFirst) { tracker.blur(); tracker.hidden() } else { tracker.hidden(); tracker.blur() }
      wait(9200)
      tracker.visible()
      tracker.focus()
      expect(sent).toEqual([{ kind: 'tab_hidden', duration_ms: 9200, client_id: 'id1' }])
    }
  })

  it('sends window_blur when the window lost focus but the tab stayed visible', () => {
    const { sent, tracker, wait } = setup()
    tracker.blur()
    wait(5000)
    tracker.focus()
    expect(sent).toEqual([{ kind: 'window_blur', duration_ms: 5000, client_id: 'id1' }])
  })

  it('ignores a short blur and a focus that has no blur', () => {
    const { sent, tracker, wait } = setup()
    tracker.focus()
    tracker.blur()
    wait(500)
    tracker.focus()
    expect(sent).toEqual([])
  })

  it('sends only the length of pasted and copied text, and nothing for an empty copy', () => {
    const { sent, tracker } = setup()
    tracker.paste(312)
    tracker.copy(0)
    tracker.copy(40)
    expect(sent).toEqual([{ kind: 'paste', chars: 312, client_id: 'id1' }, { kind: 'copy', chars: 40, client_id: 'id2' }])
    expect(JSON.stringify(sent)).not.toMatch(/text/)
  })
})
