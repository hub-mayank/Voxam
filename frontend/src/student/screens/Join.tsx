import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Button from '../../shared/Button'
import Page from '../../shared/Page'
import StudentError from '../StudentError'
import { useFocusHeading, useSecondsLeft, useStage } from '../phase'

function Join() {
  const session = useStage('login')
  const [params] = useSearchParams()
  const [vivaId, setVivaId] = useState(params.get('viva') ?? '')
  const [studentId, setStudentId] = useState('')
  const [code, setCode] = useState('')
  const [show, setShow] = useState(false)
  const [until, setUntil] = useState<number | null>(null)
  const wait = useSecondsLeft(until)
  useFocusHeading()

  // the server says how long to wait after wrong codes: keep the fields, block the button until then
  useEffect(() => {
    const ms = session.error?.retryAfterMs
    if (ms) setUntil(Date.now() + ms)
  }, [session.error])

  const blocked = session.busy || wait > 0 || !vivaId.trim() || !studentId.trim() || !code.trim()

  return (
    <Page title="Join your viva">
      <div className="student">
        <StudentError error={session.error} onDismiss={session.clearError} extra={wait > 0 ? `You can try again in ${wait} s.` : undefined} />
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault()
            if (!blocked) void session.join(vivaId, studentId, code)
          }}
        >
          <label className="field">
            Viva ID
            <input value={vivaId} onChange={(e) => setVivaId(e.target.value)} autoComplete="off" placeholder="for example local-dsa" />
          </label>
          <label className="field">
            Student ID
            <input value={studentId} onChange={(e) => setStudentId(e.target.value)} autoComplete="off" placeholder="your college ID" />
          </label>
          <label className="field">
            Access code
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              type={show ? 'text' : 'password'}
              autoComplete="off"
              placeholder="XXXX-XXXX"
            />
          </label>
          <p>
            <label>
              <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Show the code
            </label>
          </p>
          <Button type="submit" variant="primary" disabled={blocked}>
            {wait > 0 ? `Wait ${wait} s` : 'Continue'}
          </Button>
        </form>
        <p>Your faculty gave you the viva ID and a personal access code. The code works for one viva only.</p>
      </div>
    </Page>
  )
}

export default Join
