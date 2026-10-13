// Faculty login state. Wrap the faculty routes in <FacultyProvider>; screens call useFacultyApi().
// The token lives in sessionStorage (cleared when the tab closes) and is verified with GET /faculty/vivas.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { ApiError } from './client'
import { facultyApi, type FacultyApi } from './faculty'

const KEY = 'voxam.faculty.token'

function readToken(): string | null {
  try {
    return sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}

function writeToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(KEY, token)
    else sessionStorage.removeItem(KEY)
  } catch {
    // storage blocked: the login simply does not survive a reload
  }
}

export interface FacultyContextValue {
  /** null until logged in */
  api: FacultyApi | null
  token: string | null
  /** Verifies the token against the server; throws ApiError (unauthorized, network_error...) when it is not accepted. */
  login: (token: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<FacultyContextValue | null>(null)

export function FacultyProvider({ children, fetchImpl }: { children: ReactNode; fetchImpl?: typeof fetch }) {
  const [token, setToken] = useState<string | null>(readToken)

  const login = useCallback(
    async (candidate: string) => {
      const trimmed = candidate.trim()
      if (!trimmed) throw new ApiError('unauthorized', 'Enter your faculty token.', 401)
      await facultyApi(trimmed, fetchImpl).listVivas() // throws when the token is wrong
      writeToken(trimmed)
      setToken(trimmed)
    },
    [fetchImpl],
  )
  const logout = useCallback(() => {
    writeToken(null)
    setToken(null)
  }, [])

  const value = useMemo(
    () => ({ token, api: token ? facultyApi(token, fetchImpl) : null, login, logout }),
    [token, login, logout, fetchImpl],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useFacultyApi(): FacultyContextValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useFacultyApi must be used inside <FacultyProvider>')
  return v
}
