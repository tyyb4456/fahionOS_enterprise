import { useAuth } from '@clerk/clerk-react'
import { useEffect, useMemo, useRef } from 'react'

// const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8080'
const API_BASE = 'http://localhost:8080'


export function useApi() {
  const { getToken } = useAuth()
  // Keep the latest getToken without changing `api`'s identity on every render —
  // otherwise effects that depend on the api object re-run forever (request loop).
  const getTokenRef = useRef(getToken)
  useEffect(() => { getTokenRef.current = getToken }, [getToken])

  const api = useMemo(() => {
    const request = async (method, path, body = null) => {
      const token = await getTokenRef.current()

      const res = await fetch(`${API_BASE}${path}`, {
        method,
        headers: {
          'Content-Type':  'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: body ? JSON.stringify(body) : null,
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      if (res.status === 204) return null
      return res.json()
    }

    // Multipart upload (policy documents) — no manual Content-Type so the
    // browser sets the correct multipart boundary automatically.
    const upload = async (path, formData) => {
      const token = await getTokenRef.current()
      const res = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      if (res.status === 204) return null
      return res.json()
    }

    return {
      get:     (path)       => request('GET',    path),
      post:    (path, body) => request('POST',   path, body),
      put:     (path, body) => request('PUT',    path, body),
      patch:   (path, body) => request('PATCH',  path, body),
      del:     (path)       => request('DELETE', path),
      upload,
    }
  }, [])

  return api
}