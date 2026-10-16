import type { ReactNode } from 'react'

function Page({ title, actions, children, wide = false }: { title: string; actions?: ReactNode; children?: ReactNode; wide?: boolean }) {
  return (
    <main className={wide ? 'page wide' : 'page'}>
      <div className="page-head">
        <h1>{title}</h1>
        {actions}
      </div>
      {children}
    </main>
  )
}

export default Page
