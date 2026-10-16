import Button from '../../shared/Button'
import Page from '../../shared/Page'
import { useFocusHeading, useStage } from '../phase'
import ResultView from '../ResultView'

function Done() {
  const session = useStage('done')
  useFocusHeading()

  return (
    <Page title="Your viva is complete">
      <div className="student">
        <section className="card">
          <p>{session.closingText ?? 'Thank you. Your answers have been saved.'}</p>
          <p>You can safely close this page.</p>
        </section>
        {session.sessionId && session.token && <ResultView />}
        {session.transcript.length > 0 && (
          <ol className="log" aria-label="Your conversation">
            {session.transcript.map((line, i) => (
              <li key={i} className={line.role}>
                <strong>{line.role === 'ai' ? 'Interviewer' : 'You'}:</strong> {line.text}
              </li>
            ))}
          </ol>
        )}
        <p>
          <Button onClick={session.signOut}>Sign out</Button>
        </p>
      </div>
    </Page>
  )
}

export default Done
