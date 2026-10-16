import { useState } from 'react'
import { ApiError } from '../api/client'
import { useFacultyApi } from '../api/useFacultyApi'
import Button from '../shared/Button'
import ErrorBanner from '../shared/ErrorBanner'

function ExportRelease({ vivaId }: { vivaId: string }) {
  const { api, logout } = useFacultyApi()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [message, setMessage] = useState('')

  async function download() {
    if (!api || busy) return
    setBusy(true)
    setError(null)
    setMessage('')
    try {
      const csv = await api.exportCsv(vivaId)
      const objectUrl = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = 'viva-results.csv'
      document.body.appendChild(link)
      try {
        link.click()
      } finally {
        link.remove()
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
      }
      setMessage('CSV download started.')
    } catch (cause) {
      const failure = cause instanceof ApiError
        ? cause
        : new ApiError('internal_error', 'Unable to export results. Please try again.', 0)
      if (failure.status === 401) logout()
      else setError(failure)
    } finally {
      setBusy(false)
    }
  }

  if (!api) return null
  return (
    <section aria-label="Export results">
      <Button disabled={busy} onClick={() => void download()}>
        {busy ? 'Preparing CSV...' : 'Download CSV'}
      </Button>
      <ErrorBanner error={error} />
      {message && <p role="status">{message}</p>}
    </section>
  )
}

export default ExportRelease
