import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import IntegritySignals from './IntegritySignals'

afterEach(cleanup)

const events = [
  { id: 2, kind: 'paste', t_ms: 312000, detail: { chars: 312, client_id: 'b' } },
  { id: 1, kind: 'tab_hidden', t_ms: 65000, detail: { duration_ms: 9200, client_id: 'a' } },
]

describe('integrity signals', () => {
  it('says plainly when nothing was recorded', () => {
    render(<IntegritySignals events={[]} />)
    expect(screen.getByText('No signals recorded.')).toBeTruthy()
    expect(screen.getByText(/do not affect the mark/)).toBeTruthy()
  })

  it('lists the signals oldest first with a summary and neutral styling', () => {
    const { container } = render(<IntegritySignals events={events} />)
    const rows = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(rows[0]).toContain('01:05 · Tab hidden, away 9 s')
    expect(rows[1]).toContain('05:12 · Pasted text, 312 characters')
    expect(screen.getByText('2 signals').className).toContain('info')
    expect(container.textContent).toContain('1 tab hidden, 1 pasted text')
    expect(container.textContent).toContain('9 s away in total')
    expect(container.querySelector('.bad, .warn')).toBeNull()
  })

  it('offers play-from-here only when there is audio, at the signal time', () => {
    const play = vi.fn()
    const { rerender } = render(<IntegritySignals events={events} />)
    expect(screen.queryByRole('button', { name: 'Play from here' })).toBeNull()
    rerender(<IntegritySignals events={events} onPlay={play} />)
    fireEvent.click(screen.getAllByRole('button', { name: 'Play from here' })[0])
    expect(play).toHaveBeenCalledWith(65000)
  })

  it('shows an unknown kind as it came instead of hiding it', () => {
    render(<IntegritySignals events={[{ id: 1, kind: 'long_silence', t_ms: 1000, detail: {} }]} />)
    expect(screen.getByRole('listitem').textContent).toContain('long_silence')
  })
})
