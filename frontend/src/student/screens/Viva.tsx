import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Badge from '../../shared/Badge'
import Button from '../../shared/Button'
import ErrorBanner from '../../shared/ErrorBanner'
import Page from '../../shared/Page'
import { useSession } from '../session/StudentSessionProvider'

const NEXT: Record<string, string> = { rules: '../rules', ready: '../ready', done: '../done' }

function fmt(ms: number | null) {
  if (ms === null) return '–'
  return `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, '0')}`
}

function Viva() {
  const session = useSession()
  const navigate = useNavigate()
  const [text, setText] = useState('')
  useEffect(() => {
    const next = NEXT[session.phase]
    if (next) navigate(next, { replace: true })
  }, [session.phase, navigate])
  // The server decides when time is up: when the countdown hits 0, re-read status once so the viva ends cleanly.
  useEffect(() => {
    if (session.phase === 'viva' && session.remainingMs === 0) void session.refresh()
  }, [session.phase, session.remainingMs, session.refresh])
  if (session.phase === 'login') return (<Page title="Your viva"><p>You have not joined a viva yet. <Link to="..">Join</Link></p></Page>)
  const left = session.remainingMs
  return (
    <Page title={session.vivaTitle || 'Your viva'}>
      <p><Badge tone={left !== null && left <= 60000 ? 'warn' : 'info'}>Time left {fmt(left)}</Badge></p>
      <ErrorBanner error={session.error} onDismiss={session.clearError} />
      {session.currentTurn && (<div className="card"><Badge>{session.currentTurn.phase}</Badge><p>{session.currentTurn.text}</p></div>)}
      <ul>
        {session.transcript.map((line, i) => (<li key={i}><strong>{line.role === 'ai' ? 'AI' : 'You'}:</strong> {line.text}</li>))}
      </ul>
      {left !== null && left <= 60000 && <p>One minute left. Finish your current answer.</p>}
      <form onSubmit={(e) => { e.preventDefault(); void session.submitAnswer(text).then((ok) => { if (ok) setText('') }) }}>
        <label className="field">Your answer<textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} placeholder="Type your answer…" /></label>
        <Button type="submit" variant="primary" disabled={session.busy || text.trim() === ''}>Send</Button>
      </form>
      <p>If your connection drops, sending again will not record your answer twice.</p>
    </Page>
  )
}

export default Viva
