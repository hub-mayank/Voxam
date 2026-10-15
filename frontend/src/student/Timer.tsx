import { useEffect, useRef, useState } from 'react'
import { clock } from './phase'

/** The server's countdown. Words are announced twice (one minute, ten seconds) and at zero; the digits are not read every second. */
function Timer({ remainingMs }: { remainingMs: number | null }) {
  const [said, setSaid] = useState('')
  const done = useRef(new Set<number>())
  const low = remainingMs !== null && remainingMs <= 60000

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
        {low && remainingMs !== null && remainingMs > 0 && <span> (less than a minute)</span>}
      </p>
      <p className="sr-only" role="status" aria-live="polite">{said}</p>
    </>
  )
}

export default Timer
