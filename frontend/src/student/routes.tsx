// Student routes. Bhavesh: add or change routes here (and only here) when a card needs a new page.
import type { RouteObject } from 'react-router-dom'
import Done from './screens/Done'
import Join from './screens/Join'
import MicCheck from './screens/MicCheck'
import RulesConsent from './screens/RulesConsent'
import Viva from './screens/Viva'
import Waiting from './screens/Waiting'

export const studentRoutes: RouteObject[] = [
  { index: true, element: <Join /> },
  { path: 'rules', element: <RulesConsent /> },
  { path: 'ready', element: <Waiting /> },
  { path: 'mic-check', element: <MicCheck /> },
  { path: 'viva', element: <Viva /> },
  { path: 'done', element: <Done /> },
]
