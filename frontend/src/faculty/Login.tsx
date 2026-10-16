import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useFacultyApi } from '../api/useFacultyApi'
import Button from '../shared/Button'
import ErrorBanner from '../shared/ErrorBanner'
import Page from '../shared/Page'

function Login() {
  const { login } = useFacultyApi()
  const navigate = useNavigate()
  const [token, setToken] = useState('')
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (checking) return

    setError(null)
    setChecking(true)
    try {
      await login(token)
      navigate('/faculty', { replace: true })
    } catch (cause) {
      setError(cause instanceof ApiError
        ? cause
        : !token.trim()
          ? new ApiError('unauthorized', 'Enter your faculty token.', 401)
          : new ApiError('internal_error', 'Unable to log in. Please try again.', 0))
    } finally {
      setChecking(false)
    }
  }

  return (
    <Page title="Faculty login" wide>
      <form className="faculty-login-form" onSubmit={handleSubmit} aria-busy={checking}>
        <label className="field" htmlFor="faculty-token">
          Faculty token
          <input
            id="faculty-token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            disabled={checking}
          />
        </label>
        <ErrorBanner error={error} />
        <Button type="submit" variant="primary" disabled={checking}>Log in</Button>
        {checking && <p role="status">Checking token...</p>}
      </form>
    </Page>
  )
}

export default Login
