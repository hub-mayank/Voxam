import { createRef } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AudioPlayer, { type AudioPlayerHandle } from './AudioPlayer'

afterEach(() => { cleanup() })

describe('Audio replay', () => {
  it('seeks in seconds and starts playback, including offset zero', () => {
    const ref = createRef<AudioPlayerHandle>()
    const { container } = render(<AudioPlayer ref={ref} audio={{ available: true, url: '/recording' }} onRetry={() => {}} />)
    const player = container.querySelector('audio')!
    Object.defineProperty(player, 'readyState', { value: 1 })
    player.play = vi.fn().mockResolvedValue(undefined)
    act(() => ref.current?.playFrom(12500))
    expect(player.currentTime).toBe(12.5)
    act(() => ref.current?.playFrom(0))
    expect(player.currentTime).toBe(0)
    expect(player.play).toHaveBeenCalledTimes(2)
  })

  it('waits for metadata before seeking and offers fresh-link retry on media error', () => {
    const ref = createRef<AudioPlayerHandle>()
    const retry = vi.fn()
    const { container } = render(<AudioPlayer ref={ref} audio={{ available: true, url: '/recording' }} onRetry={retry} />)
    const player = container.querySelector('audio')!
    player.load = vi.fn()
    player.play = vi.fn().mockResolvedValue(undefined)
    act(() => ref.current?.playFrom(5000))
    expect(player.load).toHaveBeenCalledOnce()
    Object.defineProperty(player, 'readyState', { value: 1 })
    fireEvent.loadedMetadata(player)
    expect(player.currentTime).toBe(5)
    fireEvent.error(player)
    fireEvent.click(screen.getByRole('button', { name: 'Retry audio' }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it('explains absent audio', () => {
    const { container } = render(<AudioPlayer audio={{ available: false }} onRetry={() => {}} />)
    expect(container.querySelector('audio')).toBeNull()
    expect(screen.getByText('No audio recording is available for this session.')).toBeTruthy()
  })
})
