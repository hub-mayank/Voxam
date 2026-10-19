import type { SessionDetail } from '../api/types'
import Badge from '../shared/Badge'
import Button from '../shared/Button'

type Signal = SessionDetail['integrity_events'][number]

const LABELS: Record<string, string> = {
  tab_hidden: 'Tab hidden',
  window_blur: 'Window lost focus',
  paste: 'Pasted text',
  copy: 'Copied text',
}

function clock(ms: number) {
  const total = Math.floor(ms / 1000)
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

function describe(signal: Signal) {
  const detail = signal.detail ?? {}
  const away = typeof detail.duration_ms === 'number' ? Math.round(detail.duration_ms / 1000) : null
  const chars = typeof detail.chars === 'number' ? detail.chars : null
  if (away !== null) return `away ${away} s`
  if (chars !== null) return `${chars} characters`
  return ''
}

// facts for a human to weigh, not a verdict: neutral colours on purpose
function IntegritySignals({ events, onPlay }: { events: Signal[]; onPlay?: (ms: number) => void }) {
  const ordered = [...events].sort((a, b) => a.t_ms - b.t_ms || a.id - b.id)
  const awayMs = ordered.reduce((sum, e) => sum + (typeof e.detail?.duration_ms === 'number' ? e.detail.duration_ms : 0), 0)
  const counts = ordered.reduce<Record<string, number>>((all, e) => ({ ...all, [e.kind]: (all[e.kind] ?? 0) + 1 }), {})

  return (
    <section aria-labelledby="signals-heading">
      <h2 id="signals-heading">Signals to look at</h2>
      <p className="muted">These are facts for you to weigh. They do not affect the mark. Listen to the audio around the time before drawing a conclusion.</p>
      {ordered.length === 0 ? <p>No signals recorded.</p> : (
        <>
          <p>
            <Badge tone="info">{ordered.length} {ordered.length === 1 ? 'signal' : 'signals'}</Badge>{' '}
            {Object.entries(counts).map(([kind, n]) => `${n} ${(LABELS[kind] ?? kind).toLowerCase()}`).join(', ')}
            {awayMs > 0 && ` (${Math.round(awayMs / 1000)} s away in total)`}
          </p>
          <ul>
            {ordered.map((signal) => (
              <li key={signal.id}>
                {clock(signal.t_ms)} · {LABELS[signal.kind] ?? signal.kind}{describe(signal) && `, ${describe(signal)}`}{' '}
                {onPlay && <Button title="The position is approximate, within a few seconds" onClick={() => onPlay(signal.t_ms)}>Play from here</Button>}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

export default IntegritySignals
