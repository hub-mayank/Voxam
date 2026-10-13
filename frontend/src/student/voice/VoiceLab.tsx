// A developer page to try the voice SDK by hand: /student/voice-lab?sid=<session id>&token=<session token>[&mode=hands_free]
// (join and start a viva first; with the stub backend the AI answers with a tone). Not a student screen.
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Badge from '../../shared/Badge'
import Button from '../../shared/Button'
import ErrorBanner from '../../shared/ErrorBanner'
import Page from '../../shared/Page'
import { ApiError } from '../../api/client'
import { useVoiceSession } from './useVoiceSession'

function Lab({ sid, token, handsFree }: { sid: string; token: string; handsFree: boolean }) {
  const v = useVoiceSession({ sessionId: sid, token, mode: handsFree ? 'hands_free' : 'push_to_talk' })
  const [text, setText] = useState('')
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

function VoiceLab() {
  const [params] = useSearchParams()
  const sid = params.get('sid')
  const token = params.get('token')
  const handsFree = params.get('mode') === 'hands_free'
  if (!sid || !token) return <Page title="Voice lab"><p>Open this page as /student/voice-lab?sid=…&amp;token=…</p></Page>
  return <Lab sid={sid} token={token} handsFree={handsFree} />
}

export default VoiceLab
