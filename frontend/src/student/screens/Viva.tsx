import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/client'
import Badge from '../../shared/Badge'
import Button from '../../shared/Button'
import ErrorBanner from '../../shared/ErrorBanner'
import Page from '../../shared/Page'
import { useSession } from '../session/StudentSessionProvider'
import { useVoiceSession } from '../voice'

const NEXT: Record<string, string> = { rules: '../rules', ready: '../ready', done: '../done' }

function fmt(ms: number | null) {
  if (ms === null) return '–'
  return `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, '0')}`
}

function Viva() {
  const session = useSession()
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [voiceOn, setVoiceOn] = useState(false)
  const voice = useVoiceSession({ sessionId: session.sessionId ?? '', token: session.token ?? '' })
  const live = voiceOn && (voice.connection === 'open' || voice.connection === 'reconnecting')
  const left = live ? voice.remainingMs : session.remainingMs
  useEffect(() => {
    const next = NEXT[session.phase]
    if (next) navigate(next, { replace: true })
  }, [session.phase, navigate])
  // The server decides when time is up: when the countdown hits 0, re-read status once so the viva ends cleanly.
  useEffect(() => {
    if (session.phase === 'viva' && left === 0) void session.refresh()
  }, [session.phase, left, session.refresh])
  // A voice 'ended' does not update the HTTP session: re-read status so the screen moves to Done.
  useEffect(() => {
    if (voice.ended) void session.refresh()
  }, [voice.ended, session.refresh])
  if (session.phase === 'login') return (<Page title="Your viva"><p>You have not joined a viva yet. <Link to="..">Join</Link></p></Page>)
  return (
    <Page title={session.vivaTitle || 'Your viva'}>
      <p><Badge tone={left !== null && left <= 60000 ? 'warn' : 'info'}>Time left {fmt(left)}</Badge></p>
      <ErrorBanner error={session.error} onDismiss={session.clearError} />
      {!voiceOn && session.currentTurn && (<div className="card"><Badge>{session.currentTurn.phase}</Badge><p>{session.currentTurn.text}</p></div>)}
      {!voiceOn && (
        <ul>
          {session.transcript.map((line, i) => (<li key={i}><strong>{line.role === 'ai' ? 'AI' : 'You'}:</strong> {line.text}</li>))}
        </ul>
      )}
      {voiceOn ? (
        <div className="card">
          <p><Badge tone={voice.connection === 'open' ? 'good' : 'neutral'}>{voice.connection}</Badge>{' '}<Badge tone="info">server: {voice.serverState ?? '–'}</Badge>{' '}<Badge>{voice.aiSpeaking ? 'AI audio playing' : 'quiet'}</Badge>{' '}<Badge>level {Math.round(voice.level * 100)}</Badge>{voice.latencyMs !== null && (<>{' '}<Badge>last latency {voice.latencyMs} ms</Badge></>)}</p>
          <ErrorBanner error={voice.error ? new ApiError(voice.error.code as never, voice.error.message, 0) : null} onDismiss={voice.clearError} />
          {voice.micError && <div className="banner">{voice.micError.message} (you can still type)</div>}
          <p>
            {(voice.connection === 'idle' || voice.connection === 'closed') && <Button variant="primary" onClick={() => void voice.connect()}>Start voice</Button>}
            {live && (<><Button onPointerDown={voice.pressToTalk} onPointerUp={voice.release} onPointerLeave={voice.release} onPointerCancel={voice.release} disabled={voice.serverState !== 'listening'}>{voice.serverState === 'speaking' ? 'Hold to interrupt' : 'Hold to talk'}</Button>{' '}<Button onClick={voice.disconnect}>Stop voice</Button></>)}
          </p>
          <p>{voice.serverState === 'listening' ? 'Listening — hold the button and speak.' : voice.serverState === 'thinking' ? 'Thinking…' : voice.serverState === 'speaking' ? 'The AI is speaking — hold the button to interrupt.' : 'Voice is starting…'}</p>
          <p><strong>AI:</strong> {voice.aiText}</p>
          <ul>{voice.transcript.map((line, i) => (<li key={i}><strong>{line.role === 'student' ? 'You' : line.role === 'system' ? 'Note' : 'AI'}:</strong> {line.text}{line.confidence != null ? ` (${line.confidence})` : ''}</li>))}</ul>
        </div>
      ) : (
        <p><Button onClick={() => setVoiceOn(true)}>Use voice instead</Button></p>
      )}
      {left !== null && left <= 60000 && <p>One minute left. Finish your current answer.</p>}
      <form onSubmit={(e) => { e.preventDefault(); if (live) { voice.sendText(text); setText('') } else { void session.submitAnswer(text).then((ok) => { if (ok) setText('') }) } }}>
        <label className="field">Your answer<textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} placeholder="Type your answer…" /></label>
        <Button type="submit" variant="primary" disabled={session.busy || text.trim() === ''}>Send</Button>
      </form>
      {live ? <p>Typed answers go through the voice session too.</p> : <p>If your connection drops, sending again will not record your answer twice.</p>}
    </Page>
  )
}

export default Viva
