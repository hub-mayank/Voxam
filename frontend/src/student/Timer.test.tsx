import { cleanup, render, screen } from '@testing-library/react'
import { afterEach } from 'vitest'
import { describe, expect, it } from 'vitest'
import Timer from './Timer'

afterEach(cleanup)

describe('student viva timer', () => {
  it('shows remaining time as a progress bar and warns at one minute', () => {
    render(<Timer remainingMs={60000} totalMs={120000} />)

    const progress = screen.getByRole('progressbar', { name: 'Time remaining' })
    expect(progress.getAttribute('aria-valuenow')).toBe('50')
    expect(screen.getByText(/1 minute left/)).toBeTruthy()
    expect(screen.getByRole('timer').className).toContain('low')
  })

  it('announces each threshold once as the server countdown crosses it', () => {
    const view = render(<Timer remainingMs={61000} totalMs={120000} />)
    expect(view.container.querySelector('[role="status"]')?.textContent).toBe('')

    view.rerender(<Timer remainingMs={60000} totalMs={120000} />)
    expect(view.container.querySelector('[role="status"]')?.textContent).toBe('One minute left.')

    view.rerender(<Timer remainingMs={10000} totalMs={120000} />)
    expect(view.container.querySelector('[role="status"]')?.textContent).toBe('Ten seconds left.')

    view.rerender(<Timer remainingMs={0} totalMs={120000} />)
    expect(view.container.querySelector('[role="status"]')?.textContent).toBe('Time is up.')
  })
})
