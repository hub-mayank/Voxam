import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import type { StudentResult } from '../api/types'
import Button from '../shared/Button'
import { studentMessage } from './copy'
import { useSession } from './session/StudentSessionProvider'

type State =
  | { kind: 'loading' }
  | { kind: 'result'; result: StudentResult }
  | { kind: 'not_released' }
  | { kind: 'marking' }
  | { kind: 'error'; error: ApiError }

// the five rubric dimensions of docs/SPEC.md; any other key is shown as written
const LABELS: Record<string, string> = {
  conceptual: 'Conceptual understanding',
  depth: 'Depth and reasoning',
  problem: 'Problem solving',
  practical: 'Practical and project knowledge',
  communication: 'Communication',
}

/** The student's own marks and feedback, once faculty released them. Until then it says so kindly and can be asked again. */
function ResultView() {
  const session = useSession()
  const { result } = session
  const [state, setState] = useState<State>({ kind: 'loading' })

  const load = useCallback(async () => {
    setState({ kind: 'loading' })
    try {
      setState({ kind: 'result', result: await result() })
    } catch (e) {
      if (e instanceof ApiError && e.code === 'results_not_released') setState({ kind: 'not_released' })
      else if (e instanceof ApiError && e.code === 'invalid_state') setState({ kind: 'marking' })
      else setState({ kind: 'error', error: e instanceof ApiError ? e : new ApiError('internal_error', 'failed', 0) })
    }
  }, [result])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <section className="card" aria-label="Your result" aria-live="polite">
      {state.kind === 'loading' && <p>Loading your result…</p>}
      {state.kind === 'not_released' && (
        <p>Your result has not been released yet. Your faculty will release it when marking is done. Please check back later.</p>
      )}
      {state.kind === 'marking' && <p>Your viva is still being marked. Please check back in a little while.</p>}
      {state.kind === 'error' && <p role="alert">{studentMessage(state.error)}</p>}
      {(state.kind === 'not_released' || state.kind === 'marking' || state.kind === 'error') && (
        <Button onClick={() => void load()}>Check again</Button>
      )}
      {state.kind === 'result' && (
        <>
          <h2>Your result: {state.result.total} / 100</h2>
          {state.result.overridden && (
            <p>A faculty member changed your total after reviewing your viva. The marks below are the AI's first marking.</p>
          )}
          <ul>
            {state.result.dimensions.map((d) => (
              <li key={d.key}>
                {LABELS[d.key] ?? d.key}: {d.score} / 5 <small>(weight {d.weight}%)</small>
              </li>
            ))}
          </ul>
          <h3>Feedback</h3>
          <ul>
            {state.result.feedback.map((f, i) => (
              <li key={i}>
                {f.text}
                {f.evidence.length > 0 && <small> (from your answers at turns {f.evidence.join(', ')})</small>}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

export default ResultView
