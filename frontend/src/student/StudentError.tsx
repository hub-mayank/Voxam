import { useEffect } from 'react'
import type { ApiError } from '../api/client'
import Button from '../shared/Button'
import { studentMessage } from './copy'

/** One kind sentence and one next step. The exact code goes to the console for support, never to the student. */
function StudentError({ error, onDismiss, extra }: { error: ApiError | null; onDismiss?: () => void; extra?: string }) {
  useEffect(() => {
    if (error) console.warn('viva error', error.code, error.status)
  }, [error])
  if (!error) return null
  return (
    <div className="banner" role="alert">
      {studentMessage(error)}
      {extra && <small>{extra}</small>}
      {onDismiss && <Button onClick={onDismiss}>OK</Button>}
    </div>
  )
}

export default StudentError
