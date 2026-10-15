import { useSearchParams } from 'react-router-dom'
import Page from '../../shared/Page'
import TextViva from '../TextViva'
import VoiceViva from '../VoiceViva'
import { modeOf, useFocusHeading, useStage } from '../phase'

function Viva() {
  const session = useStage('viva')
  const [params] = useSearchParams()
  const mode = modeOf(params.get('mode'))
  useFocusHeading()

  return (
    <Page title={session.vivaTitle || 'Your viva'}>
      {mode === 'text' || !session.sessionId || !session.token ? (
        <TextViva />
      ) : (
        <VoiceViva mode={mode} sessionId={session.sessionId} token={session.token} />
      )}
    </Page>
  )
}

export default Viva
