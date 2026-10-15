import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Button from '../../shared/Button'
import ErrorBanner from '../../shared/ErrorBanner'
import Page from '../../shared/Page'
import { useSession } from '../session/StudentSessionProvider'

const NEXT: Record<string, string> = { ready: '../ready', viva: '../viva', done: '../done' }

function RulesConsent() {
  const session = useSession()
  const navigate = useNavigate()
  const [declined, setDeclined] = useState(false)
  useEffect(() => {
    const next = NEXT[session.phase]
    if (next) navigate(next, { replace: true })
  }, [session.phase, navigate])
  if (session.phase === 'login') return (<Page title="Rules and recording"><p>You have not joined a viva yet. <Link to="..">Join</Link></p></Page>)
  return (
    <Page title={session.vivaTitle || 'Rules and recording'}>
      <ErrorBanner error={session.error} onDismiss={session.clearError} />
      <div className="card">
        <p>{session.rulesText}</p>
        <p>Your voice and transcript are kept for faculty review.</p>
        {declined && <p>Nothing has started. You can still accept the rules below.</p>}
        <Button variant="primary" onClick={() => void session.accept()} disabled={session.busy}>I accept</Button>{' '}
        <Button onClick={() => setDeclined(true)}>Not now</Button>
      </div>
    </Page>
  )
}

export default RulesConsent
