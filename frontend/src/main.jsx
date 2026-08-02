import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import { ThemeProvider } from './context/ThemeContext'
import App from './App'
import './index.css'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || "pk_test_bmVhdC1wZW5ndWluLTQ5LmNsZXJrLmFjY291bnRzLmRldiQ"

ReactDOM.createRoot(document.getElementById('root')).render(
  <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </ClerkProvider>
)

// wtf