import { useEffect, useState } from 'react'
import { BrowserRouter, Link, Outlet, useLocation, useNavigate, useRoutes } from 'react-router-dom'
import { FacultyProvider } from './api/useFacultyApi'
import { useFacultyApi } from './api/useFacultyApi'
import { facultyRoutes } from './faculty/routes'
import Page from './shared/Page'
import { StudentSessionProvider } from './student/session/StudentSessionProvider'
import StudentSteps from './student/StudentSteps'
import { studentRoutes } from './student/routes'

function Home() {
  return (
    <Page title="">
      <section className="home-intro" aria-labelledby="home-title">
        <p className="home-eyebrow">Oral assessment, made clearer</p>
        <h1 id="home-title" aria-label="A thoughtful viva. A fairer way to show what you know.">A thoughtful viva.<br />A fairer way to show what you know.</h1>
        <p>Voxam gives every student the same structured questions and gives faculty a clear record to review.</p>
      </section>
      <section className="home-destinations" aria-label="Choose where to go">
        <Link className="home-card" to="/student">
          <div className="home-card-top"><span className="home-card-index">01 / STUDENT</span><span className="home-card-arrow" aria-hidden="true">↗</span></div>
          <h2>I am taking a viva</h2>
          <span>Continue to your student viva.</span>
        </Link>
        <Link className="home-card" to="/faculty">
          <div className="home-card-top"><span className="home-card-index">02 / FACULTY</span><span className="home-card-arrow" aria-hidden="true">↗</span></div>
          <h2>Faculty dashboard</h2>
          <span>Set up vivas and review student results.</span>
        </Link>
      </section>
      <ul className="home-facts" aria-label="How Voxam works">
        <li>Follow-up questions keep each conversation focused.</li>
        <li>One shared rubric makes marking consistent.</li>
        <li>Transcript and audio let faculty review each mark.</li>
      </ul>
    </Page>
  )
}

function Routes() {
  return useRoutes([
    { path: '/', element: <Home /> },
    { path: '/faculty', element: <Outlet />, children: facultyRoutes },
    { path: '/student', element: <StudentSessionProvider><StudentSteps /><Outlet /></StudentSessionProvider>, children: studentRoutes },
  ])
}

function AppLayout() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { api, logout } = useFacultyApi()
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      return localStorage.getItem('voxam.theme') === 'dark' ? 'dark' : 'light'
    } catch {
      return 'light'
    }
  })
  const section = pathname.startsWith('/faculty') ? 'Faculty' : pathname.startsWith('/student') ? 'Viva' : null
  const showSignOut = Boolean(api && pathname.startsWith('/faculty'))

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('voxam.theme', theme) } catch { /* theme still works for this page */ }
  }, [theme])

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="site-header-inner">
          <Link className="site-brand" to="/">
            <span className="site-brand-mark" aria-hidden="true"><svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M2.5 4.25 6.8 12l2.1-3.75 2.1 3.75 2.5-7.75" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/><circle cx="2.5" cy="4.25" r="1" fill="currentColor"/></svg></span>
            Voxam
          </Link>
          <div className="site-header-end">
            {section && <span className="site-section">{section}</span>}
            <button className="theme-toggle" type="button" aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`} onClick={() => setTheme((value) => value === 'light' ? 'dark' : 'light')}>
              <span aria-hidden="true">{theme === 'light' ? '◐' : '☼'}</span>{theme === 'light' ? 'Dark' : 'Light'}
            </button>
            {showSignOut && <button className="theme-toggle" type="button" onClick={() => { logout(); navigate('/faculty/login', { replace: true }) }}>Sign out</button>}
          </div>
        </div>
      </header>
      <Routes />
      <footer className="site-footer">
        <div className="site-footer-inner">
          <span>Questions about your viva? Contact your course team.</span>
          <span><a href="https://github.com/hub-mayank/ai-viva/blob/main/docs/PRIVACY.md" target="_blank" rel="noreferrer">Privacy and data use</a></span>
        </div>
      </footer>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <FacultyProvider><AppLayout /></FacultyProvider>
    </BrowserRouter>
  )
}

export default App
