import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import type { QuestionList } from '../api/types'
import { useFacultyApi } from '../api/useFacultyApi'
import Badge from '../shared/Badge'
import Button from '../shared/Button'
import ErrorBanner from '../shared/ErrorBanner'

function BankUpload({ vivaId }: { vivaId: string }) {
  const { api, logout } = useFacultyApi()
  const [bank, setBank] = useState<QuestionList | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [message, setMessage] = useState('')
  const active = useRef(false)
  const request = useRef(0)
  const retry = useRef<() => void>(() => {})

  const perform = useCallback(async (task: () => Promise<QuestionList>, success: string) => {
    const current = ++request.current
    retry.current = () => { void perform(task, success) }
    setBusy(true)
    setError(null)
    setMessage('')
    try {
      const result = await task()
      if (!active.current || current !== request.current) return
      setBank(result)
      setMessage(success)
    } catch (cause) {
      if (!active.current || current !== request.current) return
      const failure = cause instanceof ApiError ? cause : new ApiError('internal_error', 'The question bank request failed. Please retry.', 0)
      if (failure.status === 401) logout()
      else setError(failure)
    } finally {
      if (active.current && current === request.current) setBusy(false)
    }
  }, [logout])

  useEffect(() => {
    active.current = true
    if (api) void perform(() => api.listQuestions(vivaId), '')
    return () => { active.current = false }
  }, [api, vivaId, perform])

  if (!api) return null
  const rows = Array.isArray(error?.details.rows) ? error.details.rows : []
  return (
    <section aria-label="Question bank">
      <h2>Question bank</h2>
      <p>Uploads replace the whole bank. Uploading and approving are locked once a student has joined.</p>
      <form onSubmit={(event) => {
        event.preventDefault()
        if (file && !busy) void perform(() => api.uploadQuestions(vivaId, file), 'Question bank saved.')
      }}>
        <label className="field">Question bank file (.json or .csv)
          <input type="file" accept=".json,.csv" disabled={busy} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </label>
        <Button type="submit" disabled={busy || !file}>Upload bank</Button>
      </form>
      {busy && <p role="status">Loading or saving question bank...</p>}
      {message && <p role="status">{message}</p>}
      <ErrorBanner error={error} />
      {rows.length > 0 && <ul aria-label="Question bank row errors">{rows.map((row, index) => {
        const entry = row && typeof row === 'object' ? row as Record<string, unknown> : {}
        return <li key={index}>Row {String(entry.row ?? '?')}, {String(entry.field ?? 'file')}: {String(entry.message ?? 'Invalid row')}</li>
      })}</ul>}
      {error && <Button disabled={busy} onClick={() => retry.current()}>Retry bank request</Button>}
      {bank?.warnings.map((warning, index) => <p key={index}>{warning}</p>)}
      {!busy && bank?.items.length === 0 && <p>No questions uploaded.</p>}
      {bank?.items.map((question) => (
        <article className="card" key={question.id}>
          <h3>{question.id}: {question.topic}</h3>
          <p>{question.text}</p>
          <Badge tone={question.source === 'ai-draft' ? 'warn' : 'neutral'}>{question.source}</Badge>
          <ul>{question.key_points.map((point, index) => <li key={index}>{point}</li>)}</ul>
          {question.approved_by && <p>Approved by {question.approved_by}</p>}
          {question.source === 'ai-draft' && <Button disabled={busy} onClick={() => {
            void perform(() => api.approveQuestions(vivaId, [question.id]), 'Question approved.')
          }}>Approve {question.id}</Button>}
        </article>
      ))}
    </section>
  )
}

export default BankUpload
