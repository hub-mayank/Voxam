import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import type { Viva } from '../api/types'
import { useFacultyApi } from '../api/useFacultyApi'
import Button from '../shared/Button'
import ErrorBanner from '../shared/ErrorBanner'

function ExportRelease({ vivaId }: { vivaId: string }) {
  const { api, logout } = useFacultyApi()
  const [viva, setViva] = useState<Viva | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [message, setMessage] = useState('')
  const active = useRef(false)
  const request = useRef(0)
  const retry = useRef<() => void>(() => {})

  const perform = useCallback(async (task: (isCurrent: () => boolean) => Promise<void>) => {
    const current = ++request.current
    const isCurrent = () => active.current && current === request.current
    retry.current = () => { void perform(task) }
    setBusy(true)
    setError(null)
    setMessage('')
    try {
      await task(isCurrent)
    } catch (cause) {
      if (!isCurrent()) return
      const failure = cause instanceof ApiError ? cause : new ApiError('internal_error', 'The export or release request failed. Please retry.', 0)
      if (failure.status === 401) logout()
      else setError(failure)
    } finally {
      if (isCurrent()) setBusy(false)
    }
  }, [logout])

  useEffect(() => {
    active.current = true
    if (api) void perform(async (isCurrent) => {
      const result = await api.getViva(vivaId)
      if (isCurrent()) setViva(result)
    })
    return () => { active.current = false }
  }, [api, vivaId, perform])

  if (!api) return null
  return (
    <section aria-label="Export and release">
      <h2>Export and release</h2>
      {busy && <p role="status">Loading or saving...</p>}
      {message && <p role="status">{message}</p>}
      <ErrorBanner error={error} />
      {error && <Button disabled={busy} onClick={() => retry.current()}>Retry export or release</Button>}
      {!busy && !viva && !error && <p>No viva details available.</p>}
      {viva && (
        <>
          <p>{viva.title}</p>
          <label className="field">
            <span>Release results to students</span>
            <input type="checkbox" checked={viva.results_visible_to_students} disabled={busy} onChange={(event) => {
              const visible = event.target.checked
              void perform(async (isCurrent) => {
                const result = await api.setResultsVisible(vivaId, visible)
                if (isCurrent()) {
                  setViva(result)
                  setMessage(result.results_visible_to_students ? 'Results released.' : 'Results hidden.')
                }
              })
            }} />
          </label>
          <Button disabled={busy} onClick={() => {
            void perform(async (isCurrent) => {
              const csv = await api.exportCsv(vivaId)
              if (!isCurrent()) return
              const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
              const link = document.createElement('a')
              try {
                link.href = url
                link.download = `${vivaId.replace(/[^a-zA-Z0-9_-]/g, '_')}-results.csv`
                document.body.appendChild(link)
                link.click()
                setMessage('CSV download requested.')
              } finally {
                link.remove()
                window.setTimeout(() => URL.revokeObjectURL(url), 1000)
              }
            })
          }}>Download CSV</Button>
        </>
      )}
    </section>
  )
}

export default ExportRelease
