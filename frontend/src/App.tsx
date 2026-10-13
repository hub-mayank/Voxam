import { BrowserRouter, Link, Outlet, useRoutes } from 'react-router-dom'
import { FacultyProvider } from './api/useFacultyApi'
import { facultyRoutes } from './faculty/routes'
import Page from './shared/Page'
import { StudentSessionProvider } from './student/session/StudentSessionProvider'
import { studentRoutes } from './student/routes'

function Home() {
  return (
    <Page title="Voxam">
      <p>
        <Link to="/student">I am taking a viva</Link> · <Link to="/faculty">Faculty dashboard</Link>
      </p>
    </Page>
  )
}

function Routes() {
  return useRoutes([
    { path: '/', element: <Home /> },
    { path: '/faculty', element: <FacultyProvider><Outlet /></FacultyProvider>, children: facultyRoutes },
    { path: '/student', element: <StudentSessionProvider><Outlet /></StudentSessionProvider>, children: studentRoutes },
  ])
}

function App() {
  return (
    <BrowserRouter>
      <Routes />
    </BrowserRouter>
  )
}

export default App
