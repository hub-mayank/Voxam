import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import type { SessionDetail } from '../api/types'
import { useFacultyApi } from '../api/useFacultyApi'
import Button from '../shared/Button'
import ErrorBanner from '../shared/ErrorBanner'
import Modal from '../shared/Modal'

interface Props {
  detail: SessionDetail
  onReload: (detail: SessionDetail) => void
}

function ReviewActions({ detail, onReload }: Props) {
  const { api, logout } = useFacultyApi()
  const [total, setTotal] = useState('')
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [needsRefresh, setNeedsRefresh] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const active = useRef(false)
  const pending = useRef(false)
  const retry = useRef<(() => void) | null>(null)
  useEffect(() => {
    active.current = true
    return () => { active.current = false }
  }, [])

  function showError(cause: unknown) {
    const failure = cause instanceof ApiError ? cause : new ApiError('internal_error', 'The request failed. Please retry.', 0)
    if (failure.status === 401) logout()
    else setError(failure)
  }

  async function reload() {
    if (!api) return
    const updated = await api.getSession(detail.session_id)
    if (active.current) {
      onReload(updated)
      setNeedsRefresh(false)
    }
  }

  async function refreshOnly() {
    if (pending.current) return
    pending.current = true
    setBusy(true)
    setError(null)
    try { await reload() } catch (cause) { if (active.current) showError(cause) }
    finally {
      pending.current = false
      if (active.current) setBusy(false)
    }
  }

  async function run(task: () => Promise<string>) {
    if (pending.current) return
    pending.current = true
    setBusy(true)
    setError(null)
    setMessage('')
    retry.current = () => { void run(task) }
    try {
      const confirmed = await task()
      if (!active.current) return
      setMessage(confirmed)
      setNeedsRefresh(true)
      setConfirm(false)
      retry.current = () => { void refreshOnly() }
      await reload()
    } catch (cause) {
      if (active.current) showError(cause)
    } finally {
      pending.current = false
      if (active.current) setBusy(false)
    }
  }

  function invalid(message: string) {
    retry.current = null
    setMessage('')
    setError(new ApiError('validation_error', message, 422))
  }

  if (!api) return null
  const eligible = detail.status === 'scored' || detail.status === 'failed'
  const disabled = busy || needsRefresh || !eligible
  return (
    <section aria-label="Review actions">
      <h2>Review actions</h2>
      {!eligible && <p>Actions are available only for scored or failed sessions.</p>}
      {busy && <p role="status">Saving or refreshing session...</p>}
      {message && <p role="status">{message}</p>}
      {needsRefresh && <p>The action was saved; session details still need refreshing.</p>}
      <ErrorBanner error={error} />
      {error && retry.current && <Button disabled={busy} onClick={() => retry.current?.()}>{needsRefresh ? 'Retry session refresh' : 'Retry action'}</Button>}
      <form noValidate onSubmit={(event) => {
        event.preventDefault()
        if (disabled) return
        const value = Number(total)
        const explanation = reason.trim()
        if (!total.trim() || !Number.isFinite(value) || value < 0 || value > 100) return invalid('Enter a total from 0 to 100.')
        if (explanation.length < 3 || explanation.length > 2000) return invalid('Override reason must contain 3–2000 characters.')
        void run(async () => {
          const result = await api.override(detail.session_id, { new_total: value, reason: explanation })
          return `Override saved. Effective total: ${result.effective_total} / 100.`
        })
      }}>
        <h3>Override total</h3>
        <label className="field">New total (0–100)<input type="number" min={0} max={100} step="any" required value={total} disabled={disabled} onChange={(event) => setTotal(event.target.value)} /></label>
        <label className="field">Override reason<textarea required minLength={3} maxLength={2000} value={reason} disabled={disabled} onChange={(event) => setReason(event.target.value)} /></label>
        <Button type="submit" disabled={disabled}>Save override</Button>
      </form>
      <h3>Override history</h3>
      {detail.overrides.length === 0 ? <p>No overrides recorded.</p> : <ul>{detail.overrides.map((entry) => (
        <li key={entry.id}>{entry.old_total ?? 'No previous total'} → {entry.new_total}: {entry.reason} — {entry.reviewer}, {entry.at}</li>
      ))}</ul>}
      <form noValidate onSubmit={(event) => {
        event.preventDefault()
        if (disabled) return
        const text = note.trim()
        if (text.length < 3 || text.length > 2000) return invalid('Review note must contain 3–2000 characters.')
        void run(async () => {
          await api.review(detail.session_id, { note: text })
          return 'Review note saved.'
        })
      }}>
        <h3>Review note</h3>
        <label className="field">What was checked<textarea required minLength={3} maxLength={2000} value={note} disabled={disabled} onChange={(event) => setNote(event.target.value)} /></label>
        <Button type="submit" disabled={disabled}>Save review note</Button>
      </form>
      <h3>Review history</h3>
      {detail.reviews.length === 0 ? <p>No review notes recorded.</p> : <ul>{detail.reviews.map((entry) => (
        <li key={entry.id}>{entry.note} — {entry.reviewer}, {entry.at}</li>
      ))}</ul>}
      <Button disabled={disabled} onClick={() => setConfirm(true)}>Request rescore</Button>
      <Modal open={confirm} title="Confirm rescoring" onClose={() => { if (!busy) setConfirm(false) }}>
        <p>Queue this session for scoring again? Existing overrides and review notes remain in its history.</p>
        <Button disabled={disabled} onClick={() => {
          setConfirm(false)
          void run(async () => {
            const result = await api.rescore(detail.session_id)
            return `Rescoring request confirmed: ${result.job_status}. New scores are not available until processing finishes.`
          })
        }}>Confirm rescore</Button>
      </Modal>
    </section>
  )
}

export default ReviewActions
