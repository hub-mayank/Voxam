import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import type { SessionFilters } from '../api/faculty'
import type { SessionStatus, SessionSummary } from '../api/types'
import { useFacultyApi } from '../api/useFacultyApi'
import Badge from '../shared/Badge'
import Button from '../shared/Button'
import ErrorBanner from '../shared/ErrorBanner'
import Page from '../shared/Page'
import Table, { type Column } from '../shared/Table'
import BankUpload from './BankUpload'
import RosterUpload from './RosterUpload'
import ExportRelease from './ExportRelease'

// Request up to 20 sessions per page.
const PAGE_SIZE = 20
const statuses: SessionStatus[] = [
  'created', 'consented', 'in_progress', 'ended', 'scoring', 'scored', 'abandoned', 'failed',
]
const columns: Column<SessionSummary>[] = [
  {
    header: 'Student',
    cell: (session) => (
      <Link to={`/faculty/sessions/${encodeURIComponent(session.session_id)}`}>
        {session.student_id}{session.student_name ? ` — ${session.student_name}` : ''}
      </Link>
    ),
  },
  { header: 'Status', cell: (session) => session.status },
  { header: 'Score', cell: (session) => session.effective_total ?? 'Not scored' },
  {
    header: 'Review',
    cell: (session) => (
      <>
        {session.needs_review && <Badge tone="warn">Needs review</Badge>}
        {session.overridden && <Badge tone="info">Overridden</Badge>}
      </>
    ),
  },
]

function SessionList() {
  const { vivaId } = useParams<{ vivaId: string }>()
  const { api, logout } = useFacultyApi()
  const [filters, setFilters] = useState<SessionFilters>({})
  const [items, setItems] = useState<SessionSummary[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const generation = useRef(0)
  const inFlight = useRef(false)

  const load = useCallback(async (cursor: string | null) => {
    if (!api || !vivaId || inFlight.current) return
    const currentGeneration = generation.current
    inFlight.current = true
    setLoading(true)
    setError(null)
    try {
      const response = await api.listSessions(vivaId, { ...filters, limit: PAGE_SIZE, cursor })
      if (currentGeneration !== generation.current) return
      setItems((previous) => cursor === null ? response.items : [
        ...previous,
        ...response.items.filter((item) => !previous.some((row) => row.session_id === item.session_id)),
      ])
      setNextCursor(response.next_cursor ?? null)
    } catch (cause) {
      if (currentGeneration !== generation.current) return
      const failure = cause instanceof ApiError
        ? cause
        : new ApiError('internal_error', 'Unable to load sessions. Please try again.', 0)
      if (failure.status === 401) logout()
      else setError(failure)
    } finally {
      if (currentGeneration === generation.current) {
        inFlight.current = false
        setLoading(false)
      }
    }
  }, [api, vivaId, filters, logout])

  useEffect(() => {
    setItems([])
    setNextCursor(null)
    void load(null)
    return () => {
      generation.current += 1
      inFlight.current = false
    }
  }, [load])

  if (!api) return null
  if (!vivaId) return <Page title="Sessions" wide><p>No viva selected.</p></Page>

  return (
    <Page title="Sessions" wide>
      <details>
        <summary>Manage question bank</summary>
        <BankUpload key={vivaId} vivaId={vivaId} />
      </details>
      <details>
        <summary>Manage student roster</summary>
        <RosterUpload key={vivaId} vivaId={vivaId} />
      </details>
      <details>
        <summary>Export and release results</summary>
        <ExportRelease key={vivaId} vivaId={vivaId} />
      </details>
      <label className="field" htmlFor="session-status">
        Status
        <select id="session-status" value={filters.status ?? ''} onChange={(event) => {
          const status = statuses.find((value) => value === event.target.value)
          setFilters((previous) => ({ ...previous, status }))
        }}>
          <option value="">All statuses</option>
          {statuses.map((status) => <option key={status} value={status}>{status}</option>)}
        </select>
      </label>
      <label className="field" htmlFor="session-confidence">
        Low confidence
        <select id="session-confidence" value={filters.low_confidence === undefined ? '' : String(filters.low_confidence)} onChange={(event) => {
          const lowConfidence = event.target.value === '' ? undefined : event.target.value === 'true'
          setFilters((previous) => ({ ...previous, low_confidence: lowConfidence }))
        }}>
          <option value="">All sessions</option>
          <option value="true">Low confidence only</option>
          <option value="false">Not low confidence</option>
        </select>
      </label>
      <label className="field" htmlFor="session-search">
        Search student ID or name
        <input id="session-search" type="search" value={filters.search ?? ''} onChange={(event) => {
          const search = event.target.value
          setFilters((previous) => ({ ...previous, search }))
        }} />
      </label>
      {(items.length > 0 || (!loading && !error)) && (
        <Table columns={columns} rows={items} rowKey={(session) => session.session_id} empty="No sessions match these filters." />
      )}
      {loading && <p role="status">{items.length ? 'Loading more sessions...' : 'Loading sessions...'}</p>}
      <ErrorBanner error={error} />
      {error ? (
        <Button disabled={loading} onClick={() => void load(nextCursor)}>Retry</Button>
      ) : nextCursor && (
        <Button disabled={loading} onClick={() => void load(nextCursor)}>Load more</Button>
      )}
    </Page>
  )
}

export default SessionList
