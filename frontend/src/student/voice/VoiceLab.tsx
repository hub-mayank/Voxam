// A developer page to try the whole voice viva by hand, no other screens needed:
//   /student/voice-lab                      join with student ID + access code, accept the rules, start, talk
//   /student/voice-lab?sid=..&token=..      skip the join with a session you already started (&mode=hands_free for hands-free)
// With the stub backend the AI answers with a tone. Not a student screen: the real ones (BH-1/BH-2) use the same two hooks.
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useSession } from '../session/StudentSessionProvider'
import Badge from '../../shared/Badge'
import Button from '../../shared/Button'
import ErrorBanner from '../../shared/ErrorBanner'
import Page from '../../shared/Page'
import { ApiError } from '../../api/client'
import { useVoiceSession } from './useVoiceSession'

function Lab({ sid, token, handsFree, onEnded }: { sid: string; token: string; handsFree: boolean; onEnded?: () => void }) {
  const v = useVoiceSession({ sessionId: sid, token, mode: handsFree ? 'hands_free' : 'push_to_talk' })
  const [text, setText] = useState('')
  useEffect(() => {
    if (v.ended) onEnded?.()
  }, [v.ended, onEnded])
  const left = v.remainingMs === null ? '–' : `${Math.floor(v.remainingMs / 60000)}:${String(Math.floor((v.remainingMs % 60000) / 1000)).padStart(2, '0')}`
  return (
    <Page title="Voice lab">
      <p>
        <Badge tone={v.connection === 'open' ? 'good' : 'neutral'}>{v.connection}</Badge>{' '}
        <Badge tone="info">server: {v.serverState ?? '–'}</Badge> <Badge>{v.aiSpeaking ? 'AI audio playing' : 'quiet'}</Badge>{' '}
        <Badge>left {left}</Badge> <Badge>level {Math.round(v.level * 100)}</Badge> {v.latencyMs !== null && <Badge>last latency {v.latencyMs} ms</Badge>}
      </p>
      <ErrorBanner error={v.error ? new ApiError(v.error.code as never, v.error.message, 0) : null} onDismiss={v.clearError} />
      {v.micError && <div className="banner">{v.micError.message} (you can still type)</div>}
      <p>
        <Button variant="primary" onClick={() => void v.connect()} disabled={v.connection === 'open' || v.connection === 'connecting'}>Connect</Button>{' '}
        {handsFree ? (
          <Button onClick={v.endTurn}>I'm done</Button>
        ) : (
          <Button onPointerDown={v.pressToTalk} onPointerUp={v.release}>Hold to talk</Button>
        )}{' '}
        <Button onClick={v.disconnect}>Disconnect</Button>
      </p>
      <p>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="type an answer" />{' '}
        <Button onClick={() => { v.sendText(text); setText('') }}>Send text</Button>
      </p>
      <div className="card"><strong>AI:</strong> {v.aiText}</div>
      <ul>
        {v.transcript.map((l, i) => (
          <li key={i}>{l.role}: {l.text}{l.confidence != null ? ` (${l.confidence})` : ''}</li>
        ))}
      </ul>
      {v.ended && <div className="card">Ended ({v.ended.status}): {v.ended.text}</div>}
    </Page>
  )
}

function Field({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <label className="field">
      {label}
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} autoComplete="off" />
    </label>
  )
}

function ModePicker({ handsFree, onChange }: { handsFree: boolean; onChange: (v: boolean) => void }) {
  return (
    <fieldset className="field">
      <legend>How will you talk?</legend>
      <label>
        <input type="radio" name="mode" checked={!handsFree} onChange={() => onChange(false)} /> Push to talk: hold a button while you speak
      </label>
      <label>
        <input type="radio" name="mode" checked={handsFree} onChange={() => onChange(true)} /> Hands-free: it hears when you stop (use headphones)
      </label>
    </fieldset>
  )
}

function JoinFlow() {
  const session = useSession()
  const [vivaId, setVivaId] = useState('local-dsa')
  const [studentId, setStudentId] = useState('')
  const [code, setCode] = useState('')
  const [handsFree, setHandsFree] = useState(false)
  const errors = <ErrorBanner error={session.error} onDismiss={session.clearError} />

  if (session.phase === 'login') {
    return (
      <Page title="Voice lab: join">
        {errors}
        <form className="card" onSubmit={(e) => { e.preventDefault(); void session.join(vivaId, studentId, code) }}>
          <Field label="Viva ID" value={vivaId} onChange={setVivaId} />
          <Field label="Student ID" value={studentId} onChange={setStudentId} placeholder="LOCAL01" />
          <Field label="Access code" value={code} onChange={setCode} placeholder="XXXX-XXXX" />
          <Button type="submit" variant="primary" disabled={session.busy || !studentId || !code}>Join</Button>
        </form>
        <p>Local run: <code>scripts/run_local.sh</code> prints the students (LOCAL01 to LOCAL10) and their codes.</p>
      </Page>
    )
  }
  if (session.phase === 'rules') {
    return (
      <Page title={session.vivaTitle || 'Rules'}>
        {errors}
        <div className="card">
          <p>{session.rulesText}</p>
          <p>Your voice is recorded and kept for review. Headphones work best.</p>
          <Button variant="primary" onClick={() => void session.accept()} disabled={session.busy}>I accept</Button>{' '}
          <Button onClick={session.signOut}>Not now</Button>
        </div>
      </Page>
    )
  }
  if (session.phase === 'ready') {
    return (
      <Page title="Ready to start">
        {errors}
        <div className="card">
          <ModePicker handsFree={handsFree} onChange={setHandsFree} />
          <p>The 15-minute clock starts when you press Start.</p>
          <Button variant="primary" onClick={() => void session.start()} disabled={session.busy}>Start</Button>
        </div>
      </Page>
    )
  }
  if (session.phase === 'viva' && session.sessionId && session.token) {
    return (
      <>
        {errors}
        <Lab sid={session.sessionId} token={session.token} handsFree={handsFree} onEnded={() => void session.refresh()} />
      </>
    )
  }
  return (
    <Page title="Viva finished">
      <div className="card">
        <p>{session.closingText ?? 'The viva is over. Thank you.'}</p>
        <Button onClick={session.signOut}>Start over with another student</Button>
      </div>
    </Page>
  )
}

function VoiceLab() {
  const [params] = useSearchParams()
  const sid = params.get('sid')
  const token = params.get('token')
  if (sid && token) return <Lab sid={sid} token={token} handsFree={params.get('mode') === 'hands_free'} />
  return <JoinFlow />
}

export default VoiceLab
