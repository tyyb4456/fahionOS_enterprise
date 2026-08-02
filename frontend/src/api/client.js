import { useAuth } from '@clerk/clerk-react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8080'
// const API_BASE = 'http://localhost:8080'


export function useApi() {
  const { getToken } = useAuth()

  const request = async (method, path, body = null) => {
    const token = await getToken()

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

  return {
    get:   (path)       => request('GET',    path),
    post:  (path, body) => request('POST',   path, body),
    put:   (path, body) => request('PUT',    path, body),
    patch: (path, body) => request('PATCH',  path, body),
    del:   (path)       => request('DELETE', path),
  }
}