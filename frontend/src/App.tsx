import { BrowserRouter, Link, Outlet, useLocation, useRoutes } from 'react-router-dom'
import { FacultyProvider } from './api/useFacultyApi'
import { facultyRoutes } from './faculty/routes'
import Page from './shared/Page'
import { StudentSessionProvider } from './student/session/StudentSessionProvider'
import { studentRoutes } from './student/routes'

function Home() {
  return (
    <Page title="A fair, voice-first viva that your faculty can audit.">
      <section className="home-destinations" aria-label="Choose where to go">
        <Link className="home-card" to="/student">
          <h2>I am taking a viva</h2>
          <span>Continue to your student viva.</span>
        </Link>
        <Link className="home-card" to="/faculty">
          <h2>Faculty dashboard</h2>
          <span>Set up vivas and review student results.</span>
        </Link>
      </section>
      <ul className="home-facts" aria-label="How Voxam works">
        <li>It asks follow-up questions.</li>
        <li>It marks against a fixed rubric.</li>
        <li>Every mark has a transcript and audio to check.</li>
      </ul>
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

function AppLayout() {
  const { pathname } = useLocation()
  const section = pathname.startsWith('/faculty') ? 'Faculty' : pathname.startsWith('/student') ? 'Viva' : null

  return (
    <>
      <header className="site-header">
        <div className="site-header-inner">
          <Link className="site-brand" to="/">Voxam</Link>
          {section && <span className="site-section">{section}</span>}
        </div>
      </header>
      <Routes />
    </>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  )
}

export default App
