import { useEffect, useRef, useState } from 'react'
import Button from '../shared/Button'
import { useSession } from './session/StudentSessionProvider'
import StudentError from './StudentError'
import Timer from './Timer'

/** The whole viva by typing: question, answer box, history. Voice is optional everywhere else; this is the safety net. */
function TextViva() {
  const session = useSession()
  const [text, setText] = useState('')
  const refreshedAtZero = useRef(false)
  const over = session.remainingMs !== null && session.remainingMs <= 0

  // when the clock reaches zero the server decides what happens next: ask it once
  useEffect(() => {
    if (!over || refreshedAtZero.current) return
    refreshedAtZero.current = true
    void session.refresh()
  }, [over, session.refresh])

  async function send() {
    if (await session.submitAnswer(text)) setText('')
  }

  return (
    <div className="student">
      <Timer remainingMs={session.remainingMs} />
      <StudentError error={session.error} onDismiss={session.clearError} />
      <section className="card" aria-label="Question">
        <p className="question" aria-live="polite">{session.currentTurn?.text ?? 'Loading your question…'}</p>
        <label className="field">
          Your answer
          <textarea
            className="answer"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={session.busy || over}
          />
        </label>
        <Button variant="primary" disabled={session.busy || over || !text.trim()} onClick={() => void send()}>
          {session.busy ? 'Sending…' : 'Send answer'}
        </Button>
        {over && <p role="status">Time is up. Your saved answers have been kept.</p>}
      </section>
      <ol className="log" aria-label="Conversation so far">
        {session.transcript.map((line, i) => (
          <li key={i} className={line.role}>
            <strong>{line.role === 'ai' ? 'Interviewer' : 'You'}:</strong> {line.text}
          </li>
        ))}
      </ol>
    </div>
  )
}

export default TextViva
