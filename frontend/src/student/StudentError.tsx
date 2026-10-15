import { useEffect } from 'react'
import type { ApiError } from '../api/client'
import Button from '../shared/Button'
import { studentMessage } from './copy'
import { useSession } from './session/StudentSessionProvider'

// the session is gone or changed under the student: the only way forward is to sign in again
const SIGN_IN_AGAIN = new Set(['unauthorized', 'forbidden', 'rules_version_mismatch'])

/** One kind sentence and one next step. The exact code goes to the console for support, never to the student. */
function StudentError({ error, onDismiss, extra }: { error: ApiError | null; onDismiss?: () => void; extra?: string }) {
  const { signOut } = useSession()
  useEffect(() => {
    if (error) console.warn('viva error', error.code, error.status)
  }, [error])
  if (!error) return null
  return (
    <div className="banner" role="alert">
      {studentMessage(error)}
      {extra && <small>{extra}</small>}
      {SIGN_IN_AGAIN.has(error.code) ? <Button onClick={signOut}>Sign in again</Button> : onDismiss && <Button onClick={onDismiss}>OK</Button>}
    </div>
  )
}

export default StudentError
