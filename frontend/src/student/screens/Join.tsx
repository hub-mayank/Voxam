import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from '../../shared/Button'
import ErrorBanner from '../../shared/ErrorBanner'
import Page from '../../shared/Page'
import { useSession } from '../session/StudentSessionProvider'

const NEXT: Record<string, string> = { rules: 'rules', ready: 'ready', viva: 'viva', done: 'done' }

function Join() {
  const session = useSession()
  const navigate = useNavigate()
  const [vivaId, setVivaId] = useState('local-dsa')
  const [studentId, setStudentId] = useState('')
  const [code, setCode] = useState('')
  useEffect(() => {
    const next = NEXT[session.phase]
    if (next) navigate(next, { replace: true })
  }, [session.phase, navigate])
  const ready = vivaId.trim() !== '' && studentId.trim() !== '' && code.trim() !== ''
  return (
    <Page title="Join your viva">
      <ErrorBanner error={session.error} onDismiss={session.clearError} />
      <form className="card" onSubmit={(e) => { e.preventDefault(); void session.join(vivaId, studentId, code) }}>
        <label className="field">Viva ID<input value={vivaId} onChange={(e) => setVivaId(e.target.value)} autoComplete="off" /></label>
        <label className="field">Student ID<input value={studentId} onChange={(e) => setStudentId(e.target.value)} autoComplete="off" placeholder="LOCAL01" /></label>
        <label className="field">Access code<input value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" placeholder="XXXX-XXXX" /></label>
        <Button type="submit" variant="primary" disabled={session.busy || !ready}>{session.busy ? 'Joining…' : 'Join'}</Button>
      </form>
      <p>Your faculty gives you the viva ID, your student ID and a one-time access code.</p>
    </Page>
  )
}

export default Join
