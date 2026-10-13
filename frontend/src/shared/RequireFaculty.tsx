import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useFacultyApi } from '../api/useFacultyApi'

/** Faculty screens render only when logged in; otherwise go to the login page. */
function RequireFaculty({ children }: { children: ReactNode }) {
  const { api } = useFacultyApi()
  return api ? <>{children}</> : <Navigate to="/faculty/login" replace />
}

export default RequireFaculty
