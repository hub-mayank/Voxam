// TODO(BH-1): A Start button -> session.start(); the clock starts on the server.
// Hook: const session = useSession() from '../session/StudentSessionProvider'. Do not call fetch directly.
import Page from '../../shared/Page'

function Waiting() {
  return (
    <Page title="Ready to start">
      <p>Not built yet (BH-1).</p>
    </Page>
  )
}

export default Waiting
