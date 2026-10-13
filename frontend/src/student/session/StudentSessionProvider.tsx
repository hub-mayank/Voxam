// One student session for all student screens: <StudentSessionProvider> once, then useSession() in any screen.
import { createContext, useContext, type ReactNode } from 'react'
import { useStudentSession, type StudentSession } from './useStudentSession'

const Ctx = createContext<StudentSession | null>(null)

export function StudentSessionProvider({ children, fetchImpl }: { children: ReactNode; fetchImpl?: typeof fetch }) {
  const session = useStudentSession(fetchImpl)
  return <Ctx.Provider value={session}>{children}</Ctx.Provider>
}

export function useSession(): StudentSession {
  const v = useContext(Ctx)
  if (!v) throw new Error('useSession must be used inside <StudentSessionProvider>')
  return v
}
