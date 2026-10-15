import { useState } from 'react'
import { Link } from 'react-router-dom'
import Button from '../../shared/Button'
import Page from '../../shared/Page'
import { checkMicrophone } from '../voice'

type Result = { status: 'idle' } | { status: 'checking' } | { status: 'ok'; peak: number } | { status: 'failed'; message: string }

function MicCheck() {
  const [result, setResult] = useState<Result>({ status: 'idle' })
  const run = async () => {
    setResult({ status: 'checking' })
    const r = await checkMicrophone()
    setResult(r.ok ? { status: 'ok', peak: r.peak } : { status: 'failed', message: r.message })
  }
  return (
    <Page title="Microphone check">
      <div className="card">
        <p>Press the button, then speak for a moment. The meter should move while you talk.</p>
        <p><Button variant="primary" onClick={() => void run()} disabled={result.status === 'checking'}>{result.status === 'checking' ? 'Listening…' : 'Check microphone'}</Button></p>
        {result.status === 'ok' && (
          <>
            <p><progress value={result.peak} max={1} /> {Math.round(result.peak * 100)}%</p>
            {result.peak < 0.01
              ? <p>We could not hear you. Speak louder or move closer to the microphone, then check again.</p>
              : <p>Your microphone works. You are ready to talk.</p>}
          </>
        )}
        {result.status === 'failed' && (
          <>
            <div className="banner">{result.message}</div>
            <p>You can still take the viva by typing your answers.</p>
          </>
        )}
      </div>
      <p><Link to="../ready">Back</Link></p>
    </Page>
  )
}

export default MicCheck
