import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it } from 'vitest'
import { FacultyProvider, useFacultyApi } from './useFacultyApi'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function wrapperFor(fetchImpl: typeof fetch) {
  return ({ children }: { children: ReactNode }) => <FacultyProvider fetchImpl={fetchImpl}>{children}</FacultyProvider>
}

beforeEach(() => sessionStorage.clear())

describe('useFacultyApi', () => {
  it('verifies the token with GET /faculty/vivas before accepting it', async () => {
    const seen: string[] = []
    const f = (async (url: string, init: RequestInit) => {
      seen.push(`${init.method} ${new URL(String(url)).pathname} ${(init.headers as Record<string, string>).Authorization}`)
      return json({ items: [] })
    }) as unknown as typeof fetch
    const { result } = renderHook(() => useFacultyApi(), { wrapper: wrapperFor(f) })
    expect(result.current.api).toBeNull()
    await act(() => result.current.login('  good-token  '))
    expect(seen).toEqual(['GET /faculty/vivas Bearer good-token'])
    expect(result.current.api).not.toBeNull()
    expect(sessionStorage.getItem('voxam.faculty.token')).toBe('good-token')
    act(() => result.current.logout())
    expect(result.current.api).toBeNull()
  })

  it('rejects a token the server does not accept and stores nothing', async () => {
    const f = (async () => json({ error: { code: 'unauthorized', message: 'Bad token', details: {} } }, 401)) as unknown as typeof fetch
    const { result } = renderHook(() => useFacultyApi(), { wrapper: wrapperFor(f) })
    await expect(act(() => result.current.login('wrong'))).rejects.toMatchObject({ code: 'unauthorized' })
    expect(result.current.api).toBeNull()
    expect(sessionStorage.getItem('voxam.faculty.token')).toBeNull()
  })
})
