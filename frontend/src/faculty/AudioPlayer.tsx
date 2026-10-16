import { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import { apiHref, ApiError } from '../api/client'
import type { SessionDetail } from '../api/types'
import Button from '../shared/Button'
import ErrorBanner from '../shared/ErrorBanner'

export interface AudioPlayerHandle {
  playFrom: (offsetMs: number) => void
}

interface Props {
  audio: SessionDetail['audio']
  onRetry: () => void
}

const AudioPlayer = forwardRef<AudioPlayerHandle, Props>(function AudioPlayer({ audio, onRetry }, ref) {
  const player = useRef<HTMLAudioElement>(null)
  const pendingOffset = useRef<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)

  function playFrom(offsetMs: number) {
    const element = player.current
    if (!element || !Number.isFinite(offsetMs) || offsetMs < 0) return
    setError(null)
    if (element.readyState === 0) {
      pendingOffset.current = offsetMs
      setLoading(true)
      element.load()
      return
    }
    try {
      element.currentTime = offsetMs / 1000
      void element.play().catch(() => {
        setError(new ApiError('internal_error', 'Playback could not start. Try the audio controls or reload the recording.', 0))
      })
    } catch {
      setError(new ApiError('internal_error', 'This part of the recording could not be played. Reload and try again.', 0))
    }
  }

  useImperativeHandle(ref, () => ({ playFrom }))

  return (
    <section aria-label="Audio replay">
      <h2>Audio replay</h2>
      <p>Stereo recording: the left channel is the student; the right channel is the AI.</p>
      {!audio.available || !audio.url ? <p>No audio recording is available for this session.</p> : (
        <>
          <audio
            ref={player}
            controls
            preload="metadata"
            src={apiHref(audio.url)}
            onLoadedMetadata={() => {
              setLoading(false)
              if (pendingOffset.current !== null) {
                const offset = pendingOffset.current
                pendingOffset.current = null
                playFrom(offset)
              }
            }}
            onError={() => {
              setLoading(false)
              setError(new ApiError('audio_not_available', 'The recording could not be loaded. Retry to request a fresh audio link.', 0))
            }}
          />
          {loading && !error && <p role="status">Loading recording...</p>}
          <ErrorBanner error={error} />
          {error && <Button onClick={onRetry}>Retry audio</Button>}
        </>
      )}
    </section>
  )
})

export default AudioPlayer
