import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import type { SessionStatus, Viva } from '../api/types'
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
    cell: (viva) => statuses.map((status) => (
      <Badge key={status}>{status}: {viva.session_counts[status] ?? 0}</Badge>
    )),
  },
]

function VivaList() {
  const { api, logout } = useFacultyApi()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [items, setItems] = useState<Viva[]>([])

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

  return (
    <Page title="Vivas">
      {loading ? <p role="status">Loading vivas...</p> : error ? (
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
