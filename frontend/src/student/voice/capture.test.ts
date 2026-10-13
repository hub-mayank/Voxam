import { describe, expect, it } from 'vitest'
import { classifyMicError } from './capture'

describe('classifyMicError', () => {
  it.each([
    ['NotAllowedError', 'denied'],
    ['SecurityError', 'denied'],
    ['NotFoundError', 'no_device'],
    ['NotReadableError', 'busy'],
    ['TypeError', 'unsupported'],
  ])('maps %s to %s with a message a student can act on', (name, reason) => {
    const e = classifyMicError(new DOMException('x', name))
    expect(e.reason).toBe(reason)
    expect(e.message.length).toBeGreaterThan(30)
  })

  it('falls back to unknown', () => {
    expect(classifyMicError(new Error('weird')).reason).toBe('unknown')
  })
})
