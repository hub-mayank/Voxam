import { render, screen, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import StudentSteps from './StudentSteps'

afterEach(cleanup)

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><StudentSteps /></MemoryRouter>)
}

describe('student progress steps', () => {
  it.each([
    ['/student', 'Join'],
    ['/student/rules', 'Rules'],
    ['/student/ready', 'Ready'],
    ['/student/mic-check', 'Ready'],
    ['/student/viva', 'Viva'],
  ])('marks %s as the current step', (path, label) => {
    renderAt(path)
    expect(screen.getByRole('navigation', { name: 'Viva progress' })).toBeTruthy()
    expect(screen.getByRole('listitem', { name: `${label}, current` }).getAttribute('aria-current')).toBe('step')
  })

  it('shows every step complete after the viva', () => {
    renderAt('/student/done')
    const completed = screen.getAllByText('Complete', { selector: '.sr-only' })
    expect(completed).toHaveLength(4)
    expect(screen.getAllByRole('listitem', { name: /complete/ })).toHaveLength(4)
    expect(document.querySelector('[aria-current="step"]')).toBeNull()
  })

  it('does not show the exam progress on the developer voice lab', () => {
    renderAt('/student/voice-lab')
    expect(screen.queryByRole('navigation', { name: 'Viva progress' })).toBeNull()
  })
})
