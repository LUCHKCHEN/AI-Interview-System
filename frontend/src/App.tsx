import { useEffect } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation, useParams } from 'react-router-dom'
import SiteFooter from './components/SiteFooter'
import SiteNav from './components/SiteNav'
import HistoryPage from './pages/HistoryPage'
import HomePage from './pages/HomePage'
import InterviewPage from './pages/InterviewPage'
import ReportPage from './pages/ReportPage'
import SetupPage from './pages/SetupPage'

function ScrollToTop() {
  const { pathname } = useLocation()

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return null
}

function InterviewRoute() {
  const { sessionId } = useParams()

  if (!sessionId) return <Navigate to="/setup" replace />

  return <InterviewPage key={sessionId} />
}

function AppLayout() {
  return (
    <div className="app-root">
      <SiteNav />
      <main className="app-main">
        <Outlet />
      </main>
      <SiteFooter />
    </div>
  )
}

export default function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<HomePage />} />
          <Route path="setup" element={<SetupPage />} />
          <Route path="interview/:sessionId" element={<InterviewRoute />} />
          <Route path="report/:sessionId" element={<ReportPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  )
}
