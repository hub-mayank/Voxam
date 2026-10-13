// TODO(PA-1): Token field -> useFacultyApi().login(token); on success navigate('/faculty'); show ErrorBanner on ApiError.
// Hook: const { api } = useFacultyApi(). Types come from '../api/types'. Do not call fetch directly.
import Page from '../shared/Page'

function Login() {
  return (
    <Page title="Faculty login">
      <p>Not built yet (PA-1).</p>
    </Page>
  )
}

export default Login
