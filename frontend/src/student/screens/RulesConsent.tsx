import { useState } from 'react'
import Button from '../../shared/Button'
import Page from '../../shared/Page'
import StudentError from '../StudentError'
import { useFocusHeading, useStage } from '../phase'

function RulesConsent() {
  const session = useStage('rules')
  const [agree, setAgree] = useState(false)
  useFocusHeading()
  const minutes = Math.round(session.durationMs / 60000)
  const paragraphs = session.rulesText.split(/\n+/).filter((p) => p.trim())

  return (
    <Page title={session.vivaTitle || 'Before you start'}>
      <div className="student">
        <StudentError error={session.error} onDismiss={session.clearError} />
        <section className="card" aria-label="Rules">
          {paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
          <p>The viva lasts {minutes || 15} minutes. You can answer by voice or by typing.</p>
        </section>
        <p>
          <label>
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> I have read the rules and I agree to
            my voice and answers being recorded and kept for faculty review.
          </label>
        </p>
        <Button variant="primary" disabled={!agree || session.busy} onClick={() => void session.accept()}>
          I agree, continue
        </Button>{' '}
        <Button onClick={session.signOut}>Not now</Button>
      </div>
    </Page>
  )
}

export default RulesConsent
