import { useLocation } from 'react-router-dom'

const steps = ['Join', 'Rules', 'Ready', 'Viva'] as const

function stepForPath(path: string): number | null {
  if (path === '/student' || path === '/student/') return 0
  if (path === '/student/rules') return 1
  if (path === '/student/ready' || path === '/student/mic-check') return 2
  if (path === '/student/viva') return 3
  if (path === '/student/done') return steps.length
  return null
}

function StudentSteps() {
  const { pathname } = useLocation()
  const current = stepForPath(pathname)
  if (current === null) return null

  const isDone = current === steps.length

  return (
    <nav className="student-steps-wrap" aria-label="Viva progress">
      <ol className="student-steps">
        {steps.map((step, index) => {
          const complete = isDone || index < current
          const active = !isDone && index === current
          const className = `student-step${complete ? ' complete' : ''}${active ? ' current' : ''}`

          return (
            <li
              className={className}
              key={step}
              aria-current={active ? 'step' : undefined}
              aria-label={`${step}, ${complete ? 'complete' : active ? 'current' : 'upcoming'}`}
            >
              <span className="student-step-marker" aria-hidden="true">{complete ? '✓' : index + 1}</span>
              <span className="student-step-name">{step}</span>
              {active && <span className="student-step-state">Current</span>}
              {complete && <span className="sr-only">Complete</span>}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

export default StudentSteps
