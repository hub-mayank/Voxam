import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import type { SessionDetail as SessionDetailData } from '../api/types'
import { useFacultyApi } from '../api/useFacultyApi'
import Badge from '../shared/Badge'
import Button from '../shared/Button'
import ErrorBanner from '../shared/ErrorBanner'
import Page from '../shared/Page'
import AudioPlayer, { type AudioPlayerHandle } from './AudioPlayer'

function SessionDetail() {
  const { sid } = useParams<{ sid: string }>()
  const { api, logout } = useFacultyApi()
  const [detail, setDetail] = useState<SessionDetailData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState(0)
  const audioPlayer = useRef<AudioPlayerHandle>(null)

  useEffect(() => {
    if (!api || !sid) return
    const facultyApi = api
    const sessionId = sid
    let ignore = false
    setLoading(true)
    setError(null)
    setDetail(null)

    async function load() {
      try {
        const response = await facultyApi.getSession(sessionId)
        if (!ignore) setDetail(response)
      } catch (cause) {
        if (ignore) return
        const failure = cause instanceof ApiError
          ? cause
          : new ApiError('internal_error', 'Unable to load this session. Please try again.', 0)
        if (failure.status === 401) logout()
        else setError(failure)
      } finally {
        if (!ignore) setLoading(false)
      }
    }

    void load()
    return () => { ignore = true }
  }, [api, sid, logout, attempt])

  if (!api) return null
  if (!sid) return <Page title="Session detail"><p>No session selected.</p></Page>
  if (loading) return <Page title="Session detail"><p role="status">Loading session...</p></Page>
  if (error) return (
    <Page title="Session detail">
      <ErrorBanner error={error} />
      <Button onClick={() => setAttempt((previous) => previous + 1)}>Retry</Button>
    </Page>
  )
  if (!detail) return <Page title="Session detail"><p>No session data available.</p></Page>

  const turns = [...detail.turns].sort((a, b) => a.idx - b.idx)
  const turnIndexes = new Set(turns.map((turn) => turn.idx))
  const scoring = detail.scoring
  const turnId = (idx: number) => `session-${detail.session_id}-turn-${idx}`

  function showTurn(idx: number) {
    const target = document.getElementById(turnId(idx))
    if (target) {
      target.focus({ preventScroll: true })
      target.scrollIntoView({ block: 'center' })
    }
  }

  return (
    <Page title="Session detail">
      <p>{detail.student_id}{detail.student_name ? ` — ${detail.student_name}` : ''}</p>
      <p>Status: <Badge>{detail.status}</Badge></p>
      <p>
        Effective total: {detail.effective_total == null ? 'Not available' : `${detail.effective_total} / 100`}
        {detail.effective_source && ` (${detail.effective_source})`}
      </p>
      {scoring && <p>AI total: {scoring.median_total} / 100</p>}

      <section aria-labelledby="confidence-heading">
        <h2 id="confidence-heading">Review signals</h2>
        {detail.low_confidence && <Badge tone="warn">Low confidence</Badge>}
        {detail.needs_review && <Badge tone="warn">Needs review</Badge>}
        {!detail.low_confidence && !detail.needs_review && <p>No review flags reported.</p>}
        {detail.low_confidence_reasons.length > 0 ? (
          <ul>{detail.low_confidence_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
        ) : <p>No low-confidence reasons provided.</p>}
      </section>

      <section aria-labelledby="scores-heading">
        <h2 id="scores-heading">Dimension scores</h2>
        {!scoring ? <p>Scoring is not available for this session yet.</p> : (
          <>
            {scoring.dimensions.length === 0 && <p>No dimension scores provided.</p>}
            {scoring.dimensions.map((dimension) => (
              <article key={dimension.key} className="card">
                <h3>{dimension.key}: {dimension.score} / 5</h3>
                <p>{dimension.reason || 'No reason provided.'}</p>
                <p>Evidence:</p>
                {dimension.evidence.length === 0 ? <p>No evidence references provided.</p> : (
                  dimension.evidence.map((idx, index) => (
                    <Button
                      key={`${idx}-${index}`}
                      className="badge"
                      disabled={!turnIndexes.has(idx)}
                      onClick={() => showTurn(idx)}
                    >
                      Turn {idx}{!turnIndexes.has(idx) && ' (unavailable)'}
                    </Button>
                  ))
                )}
              </article>
            ))}
          </>
        )}
      </section>

      {scoring && (
        <section aria-labelledby="runs-heading">
          <h2 id="runs-heading">Scoring runs</h2>
          {scoring.runs.length === 0 ? <p>No scoring runs provided.</p> : (
            <ul>
              {[...scoring.runs].sort((a, b) => a.run - b.run).map((run) => (
                <li key={run.run}>Run {run.run}: {run.total} / 100</li>
              ))}
            </ul>
          )}
          <p>Total spread (highest run total minus lowest): {scoring.total_spread}</p>
        </section>
      )}

      <AudioPlayer ref={audioPlayer} audio={detail.audio} onRetry={() => setAttempt((previous) => previous + 1)} />
      <section aria-labelledby="transcript-heading">
        <h2 id="transcript-heading">Transcript</h2>
        {turns.length === 0 ? <p>No transcript turns available.</p> : turns.map((turn) => (
          <article key={turn.idx} id={turnId(turn.idx)} className="card" tabIndex={-1}>
            <h3>Turn {turn.idx} — {turn.role}</h3>
            <p style={{ whiteSpace: 'pre-wrap' }}>{turn.text}</p>
            {detail.audio.available && detail.audio.url && turn.t_start_ms != null && (
              <Button onClick={() => {
                if (turn.t_start_ms != null) audioPlayer.current?.playFrom(turn.t_start_ms)
              }}>Play turn {turn.idx}</Button>
            )}
          </article>
        ))}
      </section>
    </Page>
  )
}

export default SessionDetail
