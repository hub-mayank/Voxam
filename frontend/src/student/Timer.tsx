import { useEffect, useRef, useState } from 'react'
import { clock } from './phase'

/** The server's countdown. Words are announced twice (one minute, ten seconds) and at zero; the digits are not read every second. */
function Timer({ remainingMs, totalMs }: { remainingMs: number | null; totalMs: number }) {
  const [said, setSaid] = useState('')
  const done = useRef(new Set<number>())
  const low = remainingMs !== null && remainingMs <= 60000
  const progress = remainingMs === null || totalMs <= 0 ? null : Math.max(0, Math.min(100, (remainingMs / totalMs) * 100))

  useEffect(() => {
    if (remainingMs === null) return
    const marks: [number, string][] = [
      [60000, 'One minute left.'],
      [10000, 'Ten seconds left.'],
      [0, 'Time is up.'],
    ]
    for (const [at, words] of marks) {
      if (remainingMs <= at && !done.current.has(at)) {
        done.current.add(at)
        setSaid(words)
      }
    }
  }, [remainingMs])

  return (
    <>
      <p>
        Time left: <span className={`timer${low ? ' low' : ''}`} role="timer">{clock(remainingMs)}</span>
        {low && remainingMs !== null && remainingMs > 0 && <span className="timer-note"> (1 minute left)</span>}
      </p>
      {progress !== null && (
        <div
          className={`timer-track${low ? ' low' : ''}`}
          role="progressbar"
          aria-label="Time remaining"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress)}
        >
          <div className="timer-progress" style={{ width: `${progress}%` }} />
        </div>
      )}
      <p className="sr-only" role="status" aria-live="polite">{said}</p>
    </>
  )
}

export default Timer
