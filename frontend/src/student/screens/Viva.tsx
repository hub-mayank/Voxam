import { useSearchParams } from 'react-router-dom'
import Page from '../../shared/Page'
import TextViva from '../TextViva'
import VoiceViva from '../VoiceViva'
import { useIntegritySignals } from '../integrity/useIntegritySignals'
import { langOf, modeOf, useFocusHeading, useStage } from '../phase'

function Viva() {
  const session = useStage('viva')
  const [params] = useSearchParams()
  const mode = modeOf(params.get('mode'))
  const lang = langOf(params.get('lang'))
  useFocusHeading()
  useIntegritySignals(session.sessionId, session.token)

  return (
    <Page title={session.vivaTitle || 'Your viva'}>
      <p className="muted">Tab changes, paste and copy are noted for faculty review. They do not change your mark.</p>
      {mode === 'text' || !session.sessionId || !session.token ? (
        <TextViva />
      ) : (
        <VoiceViva mode={mode} language={lang} sessionId={session.sessionId} token={session.token} />
      )}
    </Page>
  )
}

export default Viva
