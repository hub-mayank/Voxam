import { useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import { studentApi } from '../../api/student'
import type { StudentResult } from '../../api/types'
import Button from '../../shared/Button'
import Page from '../../shared/Page'
import { useFocusHeading, useStage } from '../phase'

type ResultState =
  | { kind: 'loading' }
  | { kind: 'result'; result: StudentResult }
  | { kind: 'not_released' }
  | { kind: 'not_scored' }
  | { kind: 'error'; message: string }

function Done() {
  const session = useStage('done')
  const [state, setState] = useState<ResultState>({ kind: 'loading' })
  useFocusHeading()

  useEffect(() => {
    if (!session.sessionId || !session.token) return
    setState({ kind: 'loading' })
    studentApi(session.token).result(session.sessionId).then(
      (result) => setState({ kind: 'result', result }),
      (e) => {
        if (e instanceof ApiError && e.code === 'results_not_released') setState({ kind: 'not_released' })
        else if (e instanceof ApiError && e.code === 'invalid_state') setState({ kind: 'not_scored' })
        else setState({ kind: 'error', message: e instanceof Error ? e.message : 'Could not load your result.' })
      },
    )
  }, [session.sessionId, session.token])

  return (
    <Page title="Your viva is complete">
      <div className="student">
        <section className="card">
          <p>{session.closingText ?? 'Thank you. Your answers have been saved.'}</p>
          <p>You can safely close this page. Your faculty will share your result when it is released.</p>
          <Button onClick={session.signOut}>Sign out</Button>
        </section>
        {session.transcript.length > 0 && (
          <section className="card">
            <h2>Transcript</h2>
            <ul>
              {session.transcript.map((line, i) => (
                <li key={i}>
                  <strong>{line.role === 'ai' ? 'AI' : 'You'}:</strong> {line.text}
                </li>
              ))}
            </ul>
          </section>
        )}
        {state.kind === 'loading' && <p>Loading your result…</p>}
        {state.kind === 'not_released' && <p>Your result is not released yet. Your faculty will release it when marking is done — please check back later.</p>}
        {state.kind === 'not_scored' && <p>Your viva is still being marked. Please check back later.</p>}
        {state.kind === 'error' && <div className="banner" role="alert">{state.message}</div>}
        {state.kind === 'result' && (
          <section className="card">
            <h2>Your result: {state.result.total} / 100</h2>
            {state.result.overridden && <p>A faculty member changed the total; the dimension scores below are the AI's.</p>}
            <ul>
              {state.result.dimensions.map((d) => (
                <li key={d.key}>
                  {d.key}: {d.score} / 5 (weight {d.weight}%)
                </li>
              ))}
            </ul>
            <h3>Feedback</h3>
            <ul>
              {state.result.feedback.map((f, i) => (
                <li key={i}>
                  {f.text}
                  {f.evidence.length > 0 && <small> (turns {f.evidence.join(', ')})</small>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Page>
  )
}

export default Done