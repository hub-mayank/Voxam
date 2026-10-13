import type { ApiError } from '../api/client'
import Button from './Button'

/** Shows an API error: the server's message, the code (for support), and the wait time when the server gave one. */
function ErrorBanner({ error, onDismiss }: { error: ApiError | null; onDismiss?: () => void }) {
  if (!error) return null
  const wait = error.retryAfterMs
  return (
    <div className="banner" role="alert">
      {error.message}
      <small>
        {error.code}
        {wait !== null ? ` · try again in ${Math.ceil(wait / 1000)} s` : ''}
      </small>
      {onDismiss && <Button onClick={onDismiss}>Dismiss</Button>}
    </div>
  )
}

export default ErrorBanner
