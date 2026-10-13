// Faculty routes. Parth: add or change routes here (and only here) when a card needs a new page.
import type { RouteObject } from 'react-router-dom'
import RequireFaculty from '../shared/RequireFaculty'
import Login from './Login'
import SessionDetail from './SessionDetail'
import SessionList from './SessionList'
import VivaList from './VivaList'

export const facultyRoutes: RouteObject[] = [
  { path: 'login', element: <Login /> },
  { index: true, element: <RequireFaculty><VivaList /></RequireFaculty> },
  { path: 'vivas/:vivaId', element: <RequireFaculty><SessionList /></RequireFaculty> },
  { path: 'sessions/:sid', element: <RequireFaculty><SessionDetail /></RequireFaculty> },
]
