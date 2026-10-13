import type { ReactNode } from 'react'

function Badge({ tone = 'neutral', children }: { tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'info'; children: ReactNode }) {
  return <span className={`badge ${tone === 'neutral' ? '' : tone}`.trim()}>{children}</span>
}

export default Badge
