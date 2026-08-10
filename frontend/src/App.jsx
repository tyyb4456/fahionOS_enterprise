import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { SignedIn, SignedOut, RedirectToSignIn } from '@clerk/clerk-react'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import Settings from './pages/Settings'
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
          {/* <Route path="dashboard" element={<Dashboard />} /> */}
          <Route path="settings" element={<Settings />} />
          <Route path="chat" element={<Chat />} />
          <Route path="office" element={
            <Suspense fallback={
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontFamily: "'Knewave', cursive", letterSpacing: '0.08em' }}>
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