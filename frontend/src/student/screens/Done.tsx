import Button from '../../shared/Button'
import Page from '../../shared/Page'
import { useFocusHeading, useStage } from '../phase'

function Done() {
  const session = useStage('done')
  useFocusHeading()

  return (
    <Page title="Your viva is complete">
      <div className="student">
        <section className="card">
          <p>{session.closingText ?? 'Thank you. Your answers have been saved.'}</p>
          <p>You can safely close this page. Your faculty will share your result when it is released.</p>
          <Button onClick={session.signOut}>Sign out</Button>
        </section>
      </div>
    </Page>
  )
}

export default Done
