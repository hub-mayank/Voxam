import { useEffect, useState } from 'react'
import Button from '../shared/Button'
import { useSession } from './session/StudentSessionProvider'
import Timer from './Timer'
import { voiceMessage } from './copy'
import type { AnswerMode } from './phase'
import { useVoiceSession } from './voice'

const STATE_WORDS: Record<string, string> = {
  listening: 'Listening: your turn to speak',
  thinking: 'Thinking…',
  speaking: 'The interviewer is speaking',
  ended: 'The viva has ended',
}

function VoiceViva({ mode, sessionId, token }: { mode: Exclude<AnswerMode, 'text'>; sessionId: string; token: string }) {
  const session = useSession()
  const voice = useVoiceSession({ sessionId, token, mode })
  const [text, setText] = useState('')
  const [holding, setHolding] = useState(false)

  // the voice server ended the viva: re-read the session so the screen moves on
  useEffect(() => {
    if (voice.ended) void session.refresh()
  }, [voice.ended])

  // the voice socket closed or (re)opened without ending the viva: re-read the
  // session so the REST lastSeq / phase match the server. Voice answers never
  // update the REST lastSeq, and the reconnect ready message does not carry it,
  // so without this the next REST answer would use a stale seq. The open case
  // also fires on first connect (one extra status read, idempotent here because
  // this screen sends no REST answers).
  useEffect(() => {
    if (voice.ended) return
    if (voice.connection === 'closed' || voice.connection === 'open') void session.refresh()
  }, [voice.connection, voice.ended])

  const label = voice.serverState ? (voice.aiSpeaking && voice.serverState !== 'ended' ? STATE_WORDS.speaking : STATE_WORDS[voice.serverState]) : ''
  const open = voice.connection === 'open'
  const canTalk = open && voice.serverState === 'listening'
  const level = Math.min(1, voice.level * 4)
  const levelWords = voice.level < 0.02 ? 'quiet' : level > 0.9 ? 'very loud' : 'good'
  const last = voice.transcript.at(-1)

  function press() {
    if (!canTalk || holding) return
    setHolding(true)
    voice.pressToTalk()
  }

  function release() {
    if (!holding) return
    setHolding(false)
    voice.release()
  }

  return (
    <div className="student">
      <Timer remainingMs={voice.remainingMs} />
      {voice.connection === 'idle' && (
        <section className="card">
          <p>
            When you press the button the microphone turns on and the interviewer speaks the first question. If voice does not work
            you can type instead.
          </p>
          <Button variant="primary" onClick={() => void voice.connect()}>Begin the viva</Button>
        </section>
      )}
      {voice.connection === 'connecting' && <p role="status">Connecting…</p>}
      {voice.connection === 'reconnecting' && (
        <div className="banner" role="alert">Connection lost. We are trying to reconnect. The viva timer may continue.</div>
      )}
      {voice.connection === 'closed' && !voice.ended && (
        <div className="banner" role="alert">
          The voice connection closed. <Button onClick={() => void voice.connect()}>Reconnect</Button> Reconnect to keep going.
        </div>
      )}
      {voice.micError && (
        <div className="banner" role="alert">
          {voice.micError.message}
          <small>You can keep going by typing your answer below.</small>
        </div>
      )}
      {voice.error && (
        <div className="banner" role="alert">
          {voiceMessage(voice.error.message)}
          <Button onClick={voice.clearError}>OK</Button>
        </div>
      )}
      {voice.connection !== 'idle' && (
        <section className="card" aria-label="Interviewer">
          <p className="question" aria-live="polite">{voice.aiText || 'Waiting for the first question…'}</p>
          <p className="chips">
            <span className="badge info" role="status">{label || 'Connecting'}</span>
            <meter min={0} max={1} value={level} aria-label="Microphone level">{levelWords}</meter>
            <span>Microphone: {levelWords}</span>
          </p>
          {mode === 'push_to_talk' ? (
            <Button
              className={`talk${holding ? ' live' : ''}`}
              variant="primary"
              disabled={!canTalk && !holding}
              onPointerDown={press}
              onPointerUp={release}
              onPointerLeave={release}
              onPointerCancel={release}
              onKeyDown={(e) => {
                if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) {
                  e.preventDefault()
                  press()
                }
              }}
              onKeyUp={(e) => {
                if (e.key === ' ' || e.key === 'Enter') release()
              }}
            >
              {holding ? 'Release when you are done' : 'Hold to talk'}
            </Button>
          ) : (
            <Button className="talk" variant="primary" disabled={!canTalk} onClick={voice.endTurn}>
              I am done speaking
            </Button>
          )}
          {last?.role === 'student' && last.confidence != null && last.confidence < 0.6 && (
            <p role="status">We may have misheard that. You can type your answer instead if it is wrong.</p>
          )}
        </section>
      )}
      {voice.connection !== 'idle' && (
        <section className="card" aria-label="Type instead">
          <label className="field">
            Prefer to type? Write your answer here.
            <textarea className="answer" value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <Button
            disabled={!open || !text.trim() || voice.serverState !== 'listening'}
            onClick={() => {
              voice.sendText(text.trim())
              setText('')
            }}
          >
            Send typed answer
          </Button>
        </section>
      )}
      <ol className="log" aria-label="Conversation so far">
        {voice.transcript.map((line, i) => (
          <li key={i} className={line.role}>
            <strong>{line.role === 'ai' ? 'Interviewer' : line.role === 'student' ? 'You' : 'Note'}:</strong> {line.text}
          </li>
        ))}
      </ol>
    </div>
  )
}

export default VoiceViva
