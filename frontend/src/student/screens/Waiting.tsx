import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Button from '../../shared/Button'
import ErrorBanner from '../../shared/ErrorBanner'
import Page from '../../shared/Page'
import { useSession } from '../session/StudentSessionProvider'

const NEXT: Record<string, string> = { rules: '../rules', viva: '../viva', done: '../done' }

function Waiting() {
  const session = useSession()
  const navigate = useNavigate()
  useEffect(() => {
    const next = NEXT[session.phase]
    if (next) navigate(next, { replace: true })
  }, [session.phase, navigate])
  if (session.phase === 'login') return (<Page title="Ready to start"><p>You have not joined a viva yet. <Link to="..">Join</Link></p></Page>)
  return (
    <Page title={session.vivaTitle || 'Ready to start'}>
      <ErrorBanner error={session.error} onDismiss={session.clearError} />
      <div className="card">
        <p>You are checked in. The viva lasts about {Math.round(session.durationMs / 60000)} minutes, and the clock starts when you press Start.</p>
        <p>Headphones work best. You can <Link to="../mic-check">check your microphone</Link> first.</p>
        <Button variant="primary" onClick={() => void session.start()} disabled={session.busy}>Start</Button>
      </div>
    </Page>
  )
}

export default Waiting
