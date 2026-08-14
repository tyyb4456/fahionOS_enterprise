import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { SignedIn, SignedOut, RedirectToSignIn } from '@clerk/clerk-react'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import Setup from './pages/Setup'
import Dashboard from './pages/Dashboard'
import AgentDocs from './pages/AgentDocs'
import Agents from './pages/agents/Agents'
import Chat from './pages/Chat'

// three.js is ~1MB+ — only load the Virtual Office page when it's actually opened.
const Office = lazy(() => import('./pages/office/Office'))

function ProtectedRoute({ children }) {
  return (
    <>
      <SignedIn>{children}</SignedIn>
      <SignedOut><RedirectToSignIn /></SignedOut>
    </>
  )
}

// OAuth callbacks land on /settings?shopify=connected (backend FRONTEND_URL
// redirect) — settings was replaced by the setup flow, so forward with the
// query params intact for the success banners.
function SettingsRedirect() {
  const location = useLocation()
  return <Navigate to={`/setup${location.search}`} replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public landing page */}
        <Route path="/" element={<Landing />} />

        {/* Protected app shell */}
        <Route path="/" element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }>
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="setup" element={<Setup />} />
          <Route path="docs" element={<AgentDocs />} />
          <Route path="agents" element={<Agents />} />
          <Route path="settings" element={<SettingsRedirect />} />
          <Route path="chat" element={<Chat />} />
          <Route path="office" element={
            <Suspense fallback={
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", letterSpacing: '0.08em' }}>
                Loading office…
              </div>
            }>
              <Office />
            </Suspense>
          } />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}