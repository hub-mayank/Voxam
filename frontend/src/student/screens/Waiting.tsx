import { Link, useSearchParams } from 'react-router-dom'
import Button from '../../shared/Button'
import Page from '../../shared/Page'
import StudentError from '../StudentError'
import { micChecked, modeOf, useFocusHeading, useStage, type AnswerMode } from '../phase'

const OPTIONS: { value: AnswerMode; label: string; hint: string }[] = [
  { value: 'text', label: 'Type my answers', hint: 'Always available. No microphone needed.' },
  { value: 'push_to_talk', label: 'Push to talk', hint: 'Hold a button while you speak. Needs a microphone check.' },
  { value: 'hands_free', label: 'Hands-free', hint: 'It hears when you stop. Use headphones. Needs a microphone check.' },
]

function Waiting() {
  const session = useStage('ready')
  const [params, setParams] = useSearchParams()
  const mode = modeOf(params.get('mode'))
  useFocusHeading()
  const needsMic = mode !== 'text'
  const micOk = micChecked()
  const minutes = Math.round(session.durationMs / 60000)

  return (
    <Page title="Ready to start">
      <div className="student">
        <StudentError error={session.error} onDismiss={session.clearError} />
        <fieldset className="options">
          <legend>How will you answer?</legend>
          {OPTIONS.map((o) => (
            <label key={o.value}>
              <input
                type="radio"
                name="mode"
                checked={mode === o.value}
                onChange={() => setParams({ mode: o.value }, { replace: true })}
              />
              <span>
                {o.label}
                <br />
                <small>{o.hint}</small>
              </span>
            </label>
          ))}
        </fieldset>
        {needsMic && !micOk && (
          <p role="status">
            Check your microphone first. <Link to={`/student/mic-check?mode=${mode}`}>Check my microphone</Link>
          </p>
        )}
        {needsMic && micOk && <p role="status">Microphone checked.</p>}
        <p>The {minutes || 15}-minute clock starts when you press Start.</p>
        <Button variant="primary" disabled={session.busy || (needsMic && !micOk)} onClick={() => void session.start()}>
          Start the viva
        </Button>{' '}
        <Button onClick={session.signOut}>Leave</Button>
      </div>
    </Page>
  )
}

export default Waiting
