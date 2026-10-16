import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import type { SessionStatus, Viva, VivaCreate } from '../api/types'
import { useFacultyApi } from '../api/useFacultyApi'
import Badge from '../shared/Badge'
import Button from '../shared/Button'
import ErrorBanner from '../shared/ErrorBanner'
import Page from '../shared/Page'
import Table, { type Column } from '../shared/Table'

// The generated status type has no runtime list, so keep this order aligned with schema.ts.
const statuses: SessionStatus[] = [
  'created', 'consented', 'in_progress', 'ended', 'scoring', 'scored', 'abandoned', 'failed',
]

const columns: Column<Viva>[] = [
  {
    header: 'Viva',
    cell: (viva) => <Link to={`/faculty/vivas/${encodeURIComponent(viva.id)}`}>{viva.title}</Link>,
  },
  {
    header: 'Sessions by status',
    cell: (viva) => <span className="status-counts">{statuses.map((status) => {
      const tone = status === 'scored' || status === 'ended' ? 'good'
        : status === 'failed' || status === 'abandoned' ? 'bad'
          : status === 'scoring' ? 'warn' : 'neutral'
      return <Badge key={status} tone={tone}>{status.replace('_', ' ')}: {viva.session_counts[status] ?? 0}</Badge>
    })}</span>,
  },
]

function VivaList() {
  const { api, logout } = useFacultyApi()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [items, setItems] = useState<Viva[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [subject, setSubject] = useState('')
  const [vivaId, setVivaId] = useState('')
  const [topics, setTopics] = useState('')
  const [difficulty, setDifficulty] = useState<VivaCreate['difficulty']>('medium')

  useEffect(() => {
    if (!api || !loading) return
    const facultyApi = api
    let ignore = false

    async function load() {
      try {
        const response = await facultyApi.listVivas()
        if (!ignore) setItems(response.items)
      } catch (cause) {
        if (ignore) return
        const failure = cause instanceof ApiError
          ? cause
          : new ApiError('internal_error', 'Unable to load vivas. Please try again.', 0)
        if (failure.status === 401) logout()
        else setError(failure)
      } finally {
        if (!ignore) setLoading(false)
      }
    }

    void load()
    return () => { ignore = true }
  }, [api, logout, loading])

  if (!api) return null

  async function createViva(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!api || creating) return
    if (!title.trim() || !subject.trim()) {
      setCreateError('Enter a title and subject before creating the viva.')
      return
    }
    const topicList = [...new Set(topics.split(/[\n,]/).map((topic) => topic.trim()).filter(Boolean))]
    if (topicList.length === 0) {
      setCreateError('Add at least one topic, separated by commas or new lines.')
      return
    }

    setCreating(true)
    setCreateError(null)
    try {
      const body: VivaCreate = {
        title: title.trim(),
        subject: subject.trim(),
        topics: topicList,
        difficulty,
        results_visible_to_students: false,
        ...(vivaId.trim() ? { viva_id: vivaId.trim() } : {}),
      }
      const viva = await api.createViva(body)
      setItems((current) => [viva, ...current.filter((item) => item.id !== viva.id)])
      navigate(`/faculty/vivas/${encodeURIComponent(viva.id)}`)
    } catch (cause) {
      const failure = cause instanceof ApiError
        ? cause
        : new ApiError('internal_error', 'Unable to create this viva. Please try again.', 0)
      if (failure.status === 401) logout()
      else setCreateError(failure.message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <Page title="Vivas" wide actions={<Button variant="primary" aria-expanded={createOpen} aria-controls="create-viva-form" onClick={() => {
      setCreateError(null)
      setCreateOpen((open) => !open)
    }}>{createOpen ? 'Close form' : 'Create viva'}</Button>}>
      {createOpen && (
        <form id="create-viva-form" className="card" onSubmit={(event) => { void createViva(event) }} aria-label="Create a viva">
          <h2>Set up a viva</h2>
          <p>After creating it, add an approved question bank and student roster.</p>
          {createError && <p className="banner" role="alert">{createError}</p>}
          <label className="field">
            Viva title
            <input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={120} autoFocus />
          </label>
          <label className="field">
            Subject
            <input value={subject} onChange={(event) => setSubject(event.target.value)} required maxLength={120} />
          </label>
          <label className="field">
            Viva ID <span className="muted">Optional; leave blank to generate one.</span>
            <input value={vivaId} onChange={(event) => setVivaId(event.target.value)} pattern="[a-z0-9][a-z0-9-]{2,62}"
              title="Use 3–63 lowercase letters, numbers, or hyphens; start with a letter or number." />
          </label>
          <label className="field">
            Topics <span className="muted">Separate topics with commas or new lines.</span>
            <textarea value={topics} onChange={(event) => setTopics(event.target.value)} required rows={3} />
          </label>
          <label className="field">
            Difficulty
            <select value={difficulty} onChange={(event) => setDifficulty(event.target.value as VivaCreate['difficulty'])}>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
          <p className="muted">Student results stay hidden until you release them.</p>
          <div className="page-head">
            <Button type="button" disabled={creating} onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" disabled={creating}>{creating ? 'Creating…' : 'Create viva'}</Button>
          </div>
        </form>
      )}
      {loading ? <div className="skeleton-list" role="status" aria-label="Loading vivas"><span className="sr-only">Loading vivas...</span><span className="skeleton skeleton-row" /><span className="skeleton skeleton-row" /><span className="skeleton skeleton-row" /></div> : error ? (
        <>
          <ErrorBanner error={error} />
          <Button onClick={() => {
            setError(null)
            setLoading(true)
          }}>Retry</Button>
        </>
      ) : (
        <Table columns={columns} rows={items} rowKey={(viva) => viva.id} empty="No vivas yet." />
      )}
    </Page>
  )
}

export default VivaList
