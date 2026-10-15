import { useSearchParams } from 'react-router-dom'
import Page from '../../shared/Page'
import TextViva from '../TextViva'
import VoiceViva from '../VoiceViva'
import { langOf, modeOf, useFocusHeading, useStage } from '../phase'

function Viva() {
  const session = useStage('viva')
  const [params] = useSearchParams()
  const mode = modeOf(params.get('mode'))
  const lang = langOf(params.get('lang'))
  useFocusHeading()

  return (
    <Page title={session.vivaTitle || 'Your viva'}>
      {mode === 'text' || !session.sessionId || !session.token ? (
        <TextViva />
      ) : (
        <VoiceViva mode={mode} language={lang} sessionId={session.sessionId} token={session.token} />
      )}
    </Page>
  )
}

export default Viva
