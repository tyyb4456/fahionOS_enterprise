// frontend/src/pages/office/useOfficeFeed.js
// Live activity feed for the Virtual AI Office. Connects to
// GET /api/v1/office/stream (SSE over fetch — lets us send the Clerk
// Authorization header, same trick as the chat page) and keeps a per-agent
// status/action store that the 3D scene consumes.
import { useEffect, useRef, useCallback, useState } from 'react'
import { AGENT_ORDER } from './config'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8080'
const DONE_LINGER_MS = 6000
const MAX_MESSAGES = 12
const MAX_ACTIVITY = 60
const MAX_NOTIFICATIONS = 8

const IDLE = { status: 'idle', action: '' }

function idleAgents() {
  const map = {}
  for (const key of AGENT_ORDER) map[key] = { ...IDLE }
  return map
}

export function useOfficeFeed({ getToken, enabled = true }) {
  const [connected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState(null)
  const [supervisor, setSupervisor] = useState({ status: 'idle', action: 'Standing by' })
  const [agents, setAgents] = useState(() => idleAgents())
  const [messages, setMessages] = useState([])
  const [activity, setActivity] = useState([])
  const [notifications, setNotifications] = useState([])
  const [packets, setPackets] = useState([])

  const timersRef = useRef({})
  const abortRef = useRef(null)
  const aliveRef = useRef(true)
  const retryRef = useRef(0)

  const clearTimers = useCallback(() => {
    Object.values(timersRef.current).forEach(clearTimeout)
    timersRef.current = {}
  }, [])

  const addNotification = useCallback((notif) => {
    setNotifications(prev => [{ id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, ...notif }, ...prev].slice(0, MAX_NOTIFICATIONS))
  }, [])

  const applyEvent = useCallback((evt) => {
    const t = evt.type
    if (t === 'snapshot') {
      const d = evt.data || {}
      setSupervisor({ status: 'idle', action: 'Standing by', ...(d.supervisor || {}) })
      const next = idleAgents()
      for (const [key, val] of Object.entries(d.agents || {})) {
        if (next[key]) next[key] = { ...IDLE, ...val }
      }
      setAgents(next)
      setActivity((d.activity || []).slice(-MAX_ACTIVITY))
      setConnected(true)
      return
    }

    if (t === 'run.start') {
      clearTimers()
      setAgents(idleAgents())
      setSupervisor({ status: 'working', action: 'Received task' })
      setMessages([])
      setActivity(a => [evt, ...a].slice(0, MAX_ACTIVITY))
      return
    }

    if (t === 'supervisor.status') {
      setSupervisor({ status: evt.status || 'idle', action: evt.action || '' })
      if (evt.status === 'error') addNotification({ agent: 'supervisor', kind: 'error', text: 'Run failed' })
      setActivity(a => [evt, ...a].slice(0, MAX_ACTIVITY))
      return
    }

    if (t === 'agent.status') {
      const key = evt.agent
      setAgents(prev => ({ ...prev, [key]: { ...prev[key], status: evt.status, action: evt.action || '', node: evt.node } }))
      if (evt.status === 'done') {
        clearTimeout(timersRef.current[key])
        timersRef.current[key] = setTimeout(() => {
          setAgents(prev => (prev[key]?.status === 'done' ? { ...prev, [key]: { ...prev[key], status: 'idle', action: '' } } : prev))
        }, DONE_LINGER_MS)
        addNotification({ agent: key, kind: 'done', text: `${evt.action || 'Analysis'} complete` })
      } else if (evt.status === 'error') {
        addNotification({ agent: key, kind: 'error', text: evt.action || 'Failed' })
      }
      setActivity(a => [evt, ...a].slice(0, MAX_ACTIVITY))
      return
    }

    if (t === 'agent.tool') {
      const key = evt.agent
      setAgents(prev => ({ ...prev, [key]: { ...prev[key], lastTool: evt.tool, lastToolStatus: evt.status } }))
      setActivity(a => [evt, ...a].slice(0, MAX_ACTIVITY))
      return
    }

    if (t === 'agent.message') {
      const msg = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, from: evt.from, to: evt.to, kind: evt.kind, text: evt.text, ts: evt.ts }
      setMessages(prev => [msg, ...prev].slice(0, MAX_MESSAGES))
      setPackets(prev => [...prev, msg])
      setTimeout(() => setPackets(prev => prev.filter(p => p.id !== msg.id)), 1800)
      const recipient = evt.to === 'supervisor' ? 'supervisor' : evt.to
      if (evt.kind === 'reply') addNotification({ agent: 'supervisor', kind: 'message', text: `${msg.from} reported back` })
      else if (evt.kind === 'task') addNotification({ agent: recipient, kind: 'message', text: 'New task from supervisor' })
      setActivity(a => [evt, ...a].slice(0, MAX_ACTIVITY))
      return
    }

    if (t === 'run.end') {
      setActivity(a => [evt, ...a].slice(0, MAX_ACTIVITY))
    }
  }, [addNotification, clearTimers])

  const connect = useCallback(async () => {
    if (!aliveRef.current) return
    setConnecting(true)
    setError(null)
    try {
      const token = await getToken()
      if (abortRef.current) abortRef.current.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl

      const res = await fetch(`${API_BASE}/api/v1/office/stream`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: ctrl.signal,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      setConnecting(false)
      setConnected(true)
      retryRef.current = 0

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          let evt
          try { evt = JSON.parse(raw) } catch { continue }
          applyEvent(evt)
        }
      }
      setConnected(false)
    } catch (err) {
      if (err.name === 'AbortError') return
      setConnected(false)
      setError(err.message || 'Connection lost')
    } finally {
      setConnecting(false)
    }
  }, [getToken, applyEvent])

  // Auto-connect + reconnect with backoff.
  useEffect(() => {
    if (!enabled) return
    aliveRef.current = true
    let timer = null
    let cancelled = false

    const loop = async () => {
      if (cancelled) return
      await connect()
      if (cancelled) return
      const delay = Math.min(1500 * 2 ** Math.min(retryRef.current, 4), 15000)
      retryRef.current += 1
      timer = setTimeout(loop, delay)
    }
    loop()

    return () => {
      cancelled = true
      clearTimeout(timer)
      if (abortRef.current) abortRef.current.abort()
      aliveRef.current = false
      clearTimers()
    }
  }, [enabled, connect, clearTimers])

  const retryNow = useCallback(async () => {
    retryRef.current = 0
    await connect()
  }, [connect])

  const markRead = useCallback((agentKey) => {
    setNotifications(prev => prev.filter(n => n.agent !== agentKey))
  }, [])

  const markAllRead = useCallback(() => {
    setNotifications([])
  }, [])

  return {
    connected, connecting, error,
    supervisor, agents, messages, activity, notifications, packets,
    retryNow, markRead, markAllRead,
  }
}
