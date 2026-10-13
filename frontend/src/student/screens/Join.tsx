// TODO(BH-1): Fields: viva id, student id, access code -> useSession().join(...). On success go to the next screen for session.phase.
// Hook: const session = useSession() from '../session/StudentSessionProvider'. Do not call fetch directly.
import Page from '../../shared/Page'

function Join() {
  return (
    <Page title="Join your viva">
      <p>Not built yet (BH-1).</p>
    </Page>
  )
}

export default Join
