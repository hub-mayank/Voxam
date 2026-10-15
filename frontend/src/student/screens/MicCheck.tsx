import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import Button from '../../shared/Button'
import Page from '../../shared/Page'
import { recordSample, type Sample } from '../micSample'
import { modeOf, setMicChecked, useFocusHeading, useStage } from '../phase'
import { checkMicrophone } from '../voice'

type Step =
  | { kind: 'idle' }
  | { kind: 'listening' }
  | { kind: 'failed'; message: string }
  | { kind: 'quiet' }
  | { kind: 'recording' }
  | { kind: 'playback'; url: string | null; level: 'good' | 'loud' }

const QUIET = 0.02
const LOUD = 0.9

function MicCheck() {
  useStage('ready')
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const mode = modeOf(params.get('mode'))
  const [step, setStep] = useState<Step>({ kind: 'idle' })
  const sample = useRef<Sample | null>(null)
  useFocusHeading()

  useEffect(() => () => sample.current?.stop(), [])

  async function run() {
    sample.current?.stop()
    sample.current = null
    setStep({ kind: 'listening' })
    const result = await checkMicrophone(2500)
    if (!result.ok) {
      setStep({ kind: 'failed', message: result.message })
      return
    }
    if (result.peak < QUIET) {
      setStep({ kind: 'quiet' })
      return
    }
    setStep({ kind: 'recording' })
    try {
      sample.current = await recordSample()
    } catch {
      sample.current = null
    }
    setStep({ kind: 'playback', url: sample.current?.url ?? null, level: result.peak > LOUD ? 'loud' : 'good' })
  }

  function confirm() {
    setMicChecked(true)
    navigate(`/student/ready?mode=${mode === 'text' ? 'push_to_talk' : mode}`, { replace: true })
  }

  return (
    <Page title="Check your microphone">
      <div className="student">
        <p>We will listen for a moment and then play back a short recording so you can hear what we hear. Nothing is saved.</p>
        <p className="sr-only" role="status">
          {step.kind === 'listening' ? 'Listening. Please say a sentence.' : step.kind === 'recording' ? 'Recording a short sample.' : ''}
        </p>
        {step.kind === 'idle' && (
          <Button variant="primary" onClick={() => void run()}>
            Start the check
          </Button>
        )}
        {step.kind === 'listening' && <p>Listening… please say a sentence, for example "I am ready for my viva".</p>}
        {step.kind === 'recording' && <p>Recording a short sample… keep talking.</p>}
        {step.kind === 'failed' && (
          <div className="banner" role="alert">
            {step.message}
            <small>You can still take the viva by typing.</small>
          </div>
        )}
        {step.kind === 'quiet' && (
          <div className="banner" role="alert">
            We cannot hear you yet. Check your input device and speak a little louder, then try again.
          </div>
        )}
        {step.kind === 'playback' && (
          <div className="card">
            {step.level === 'loud' && <p role="status">Your voice is very loud. Move back a little or lower the input volume.</p>}
            {step.url ? (
              <>
                <p>Press play. Can you hear yourself clearly?</p>
                <audio controls src={step.url} />
              </>
            ) : (
              <p>Your microphone works. This browser cannot play back a sample, so we skip that step.</p>
            )}
            <p>
              <Button variant="primary" onClick={confirm}>
                {step.url ? 'Yes, I can hear myself' : 'Continue'}
              </Button>{' '}
              <Button onClick={() => void run()}>Try again</Button>
            </p>
          </div>
        )}
        {(step.kind === 'failed' || step.kind === 'quiet') && (
          <p>
            <Button onClick={() => void run()}>Try again</Button>{' '}
            <Button onClick={() => navigate('/student/ready?mode=text', { replace: true })}>Type my answers instead</Button>
          </p>
        )}
      </div>
    </Page>
  )
}

export default MicCheck
