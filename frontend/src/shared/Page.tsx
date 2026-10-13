import type { ReactNode } from 'react'

function Page({ title, actions, children }: { title: string; actions?: ReactNode; children?: ReactNode }) {
  return (
    <main className="page">
      <div className="page-head">
        <h1>{title}</h1>
        {actions}
      </div>
      {children}
    </main>
  )
}

export default Page
