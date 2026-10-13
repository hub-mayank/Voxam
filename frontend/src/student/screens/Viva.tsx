// TODO(BH-1/BH-2): Show session.currentTurn, session.remainingMs, typed answer -> session.submitAnswer(text). BH-2 adds voice via useVoiceSession.
// Hook: const session = useSession() from '../session/StudentSessionProvider'. Do not call fetch directly.
import Page from '../../shared/Page'

function Viva() {
  return (
    <Page title="Your viva">
      <p>Not built yet (BH-1/BH-2).</p>
    </Page>
  )
}

export default Viva
