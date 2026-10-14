import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import type { RosterList, RosterUploadResult } from '../api/types'
import { useFacultyApi } from '../api/useFacultyApi'
import Button from '../shared/Button'
import ErrorBanner from '../shared/ErrorBanner'

function RosterUpload({ vivaId }: { vivaId: string }) {
  const { api, logout } = useFacultyApi()
  const [roster, setRoster] = useState<RosterList | null>(null)
  const [issued, setIssued] = useState<RosterUploadResult | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [message, setMessage] = useState('')
  const [copyMessage, setCopyMessage] = useState('')
  const active = useRef(false)
  const request = useRef(0)
  const retry = useRef<() => void>(() => {})

  const perform = useCallback(async (task: () => Promise<void>) => {
    const current = ++request.current
    retry.current = () => { void perform(task) }
    setBusy(true)
    setError(null)
    try {
      await task()
    } catch (cause) {
      if (!active.current || current !== request.current) return
      const failure = cause instanceof ApiError ? cause : new ApiError('internal_error', 'The roster request failed. Please retry.', 0)
      if (failure.status === 401) logout()
      else setError(failure)
    } finally {
      if (active.current && current === request.current) setBusy(false)
    }
  }, [logout])

  const refresh = useCallback(async () => {
    if (!api) return
    const current = request.current
    const result = await api.listRoster(vivaId)
    if (active.current && current === request.current) setRoster(result)
  }, [api, vivaId])

  useEffect(() => {
    active.current = true
    void perform(refresh)
    return () => { active.current = false }
  }, [perform, refresh])

  async function upload() {
    if (!api || !file) return
    setMessage('')
    setIssued(null)
    setCopyMessage('')
    const current = request.current
    const result = await api.uploadRoster(vivaId, file)
    if (!active.current || current !== request.current) return
    setIssued(result)
    setMessage(`Roster saved: ${result.created} created, ${result.unchanged} unchanged.`)
    // A failed refresh must retry the read, not issue codes a second time.
    retry.current = () => { void perform(refresh) }
    await refresh()
  }

  if (!api) return null
  const rows = Array.isArray(error?.details.rows) ? error.details.rows : []
  return (
    <section aria-label="Student roster">
      <h2>Student roster</h2>
      <form onSubmit={(event) => {
        event.preventDefault()
        if (file && !busy) void perform(upload)
      }}>
        <label className="field">Roster CSV (student_id,name)
          <input type="file" accept=".csv" disabled={busy || issued !== null} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </label>
        <Button type="submit" disabled={busy || !file || issued !== null}>Upload roster</Button>
      </form>
      {busy && <p role="status">Loading or saving roster...</p>}
      {message && <p role="status">{message}</p>}
      <ErrorBanner error={error} />
      {rows.length > 0 && <ul aria-label="Roster row errors">{rows.map((row, index) => {
        const entry = row && typeof row === 'object' ? row as Record<string, unknown> : {}
        return <li key={index}>Row {String(entry.row ?? '?')}, {String(entry.field ?? 'file')}: {String(entry.message ?? 'Invalid row')}</li>
      })}</ul>}
      {error && <Button disabled={busy} onClick={() => retry.current()}>Retry roster request</Button>}
      {issued && (
        <div className="card">
          <h3>Newly issued access codes</h3>
          <p>Copy these now. They are held only in this view, not saved in browser storage. Dismissing or leaving this page clears them.</p>
          {issued.items.map((entry) => (
            <p key={entry.student_id}>
              {entry.student_id}: {entry.access_code ?? 'No new code issued'}
              {entry.access_code && <Button onClick={async () => {
                setCopyMessage('')
                try {
                  await navigator.clipboard.writeText(entry.access_code!)
                  if (active.current) setCopyMessage('Code copied.')
                } catch {
                  if (active.current) setCopyMessage('Copy failed. Select the code and copy it manually, or try Copy again.')
                }
              }}>Copy code for {entry.student_id}</Button>}
            </p>
          ))}
          {copyMessage && <p role="status">{copyMessage}</p>}
          <Button onClick={() => { setIssued(null) }}>Dismiss codes</Button>
        </div>
      )}
      {!busy && roster?.items.length === 0 && <p>No students uploaded.</p>}
      <ul>{roster?.items.map((entry) => <li key={entry.student_id}>{entry.student_id} {entry.name} — {entry.session_status ?? 'Not joined'}</li>)}</ul>
    </section>
  )
}

export default RosterUpload
