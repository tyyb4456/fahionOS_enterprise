import { useState, useRef, useEffect, useCallback } from 'react'
import { useAuth, useUser } from '@clerk/clerk-react'
import { Loader2, Menu } from 'lucide-react'
import { SUGGESTIONS } from './chat/constants'
import { uuidv4 } from './chat/utils'
import MessageBubble from './chat/MessageBubble'
import ConversationsSidebar from './chat/ConversationsSidebar'
import ChatComposer from './chat/ChatComposer'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8080'
// const API_BASE = 'http://localhost:8080'

function getGreeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Morning'
  if (hour < 17) return 'Afternoon'
  return 'Evening'
}

// Copper asterisk / starburst icon (Claude-inspired)
function AsteriskLogo({ size = 40, color = '#d4d4d8' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M20 4 L20 36" stroke={color} strokeWidth="3.2" strokeLinecap="round"/>
      <path d="M4 20 L36 20" stroke={color} strokeWidth="3.2" strokeLinecap="round"/>
      <path d="M8.69 8.69 L31.31 31.31" stroke={color} strokeWidth="3.2" strokeLinecap="round"/>
      <path d="M31.31 8.69 L8.69 31.31" stroke={color} strokeWidth="3.2" strokeLinecap="round"/>
      <path d="M5.36 12.32 L34.64 27.68" stroke={color} strokeWidth="1.6" strokeLinecap="round" opacity="0.5"/>
      <path d="M34.64 12.32 L5.36 27.68" stroke={color} strokeWidth="1.6" strokeLinecap="round" opacity="0.5"/>
      <path d="M12.32 5.36 L27.68 34.64" stroke={color} strokeWidth="1.6" strokeLinecap="round" opacity="0.5"/>
      <path d="M27.68 5.36 L12.32 34.64" stroke={color} strokeWidth="1.6" strokeLinecap="round" opacity="0.5"/>
    </svg>
  )
}

export default function Chat() {
  const { getToken } = useAuth()
  const { user } = useUser()

  const [messages,    setMessages]    = useState([])
  const [input,       setInput]       = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [threadId,    setThreadId]    = useState(() => uuidv4())

  const [conversations,    setConversations]    = useState([])
  const [convosLoading,    setConvosLoading]    = useState(true)
  const [messagesLoading,  setMessagesLoading]  = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [isMobile,         setIsMobile]         = useState(false)

  const messagesEndRef = useRef(null)
  const inputRef       = useRef(null)
  const abortRef       = useRef(null)

  const greeting = getGreeting()
  const firstName = user?.firstName || 'there'

  // Track mobile viewport
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth <= 768
      setIsMobile(mobile)
      setSidebarCollapsed(mobile)
    }
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Fetch conversations on mount
  const fetchConversations = useCallback(async () => {
    try {
      const token = await getToken()
      const res   = await fetch(`${API_BASE}/api/v1/conversations`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setConversations(data)
      }
    } catch { /* backend not connected in dev — show empty list */ }
    finally { setConvosLoading(false) }
  }, [getToken])

  useEffect(() => { fetchConversations() }, [fetchConversations])

  // Load a conversation's messages
  const selectConversation = useCallback(async (tid) => {
    if (tid === threadId && messages.length > 0) return
    if (abortRef.current) abortRef.current.abort()
    setIsStreaming(false)
    setThreadId(tid)
    setMessages([])
    if (isMobile) setSidebarCollapsed(true)

    setMessagesLoading(true)
    try {
      const token = await getToken()
      const res   = await fetch(`${API_BASE}/api/v1/conversations/${tid}/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const msgs = await res.json()
        setMessages(msgs.map((m, i) => ({
          id:        i,
          role:      m.role,
          content:   m.content,
          streaming: false,
          toolCalls: (m.tool_results || []).map((tr, j) => ({
            id: `${i}-${j}-${tr.name}`, name: tr.name, args: {}, status: 'done', data: tr.data,
          })),
          reasoning: m.reasoning || '',
        })))
      }
    } catch { /* network / dev fallback */ }
    finally { setMessagesLoading(false) }
  }, [getToken, threadId, messages.length, isMobile])

  // Delete conversation
  const deleteConversation = useCallback(async (tid) => {
    try {
      const token = await getToken()
      await fetch(`${API_BASE}/api/v1/conversations/${tid}`, {
        method:  'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
    } catch { /* ignore */ }

    setConversations(prev => prev.filter(c => c.thread_id !== tid))
    if (tid === threadId) {
      setThreadId(uuidv4())
      setMessages([])
    }
  }, [getToken, threadId])

  // New thread
  const newThread = () => {
    if (abortRef.current) abortRef.current.abort()
    setIsStreaming(false)
    setThreadId(uuidv4())
    setMessages([])
    if (isMobile) setSidebarCollapsed(true)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  // Send & stream
  const sendMessage = useCallback(async (text) => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming) return

    setInput('')
    setIsStreaming(true)

    const userMsg = { id: Date.now(), role: 'user', content: trimmed }
    const asstId  = Date.now() + 1
    setMessages(prev => [...prev,
      userMsg,
      { id: asstId, role: 'assistant', content: '', toolCalls: [], reasoning: '', streaming: true },
    ])

    try {
      const token = await getToken()
      if (abortRef.current) abortRef.current.abort()
      const ctrl     = new AbortController()
      abortRef.current = ctrl

      const res = await fetch(`${API_BASE}/api/v1/chat/stream`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body:    JSON.stringify({ message: trimmed, thread_id: threadId }),
        signal:  ctrl.signal,
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''

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

          switch (evt.type) {
            case 'token':
              setMessages(prev => prev.map(m =>
                m.id === asstId ? { ...m, content: m.content + evt.content } : m
              ))
              break
            case 'reasoning':
              setMessages(prev => prev.map(m =>
                m.id === asstId ? { ...m, reasoning: (m.reasoning || '') + evt.content } : m
              ))
              break
            case 'tool_call':
              setMessages(prev => prev.map(m =>
                m.id === asstId
                  ? { ...m, toolCalls: [...(m.toolCalls || []), { id: evt.id, name: evt.name, args: evt.args, status: 'running', data: null }] }
                  : m
              ))
              break
            case 'tool_result':
              setMessages(prev => prev.map(m =>
                m.id === asstId
                  ? { ...m, toolCalls: (m.toolCalls || []).map(c => c.id === evt.id ? { ...c, status: 'done', data: evt.data } : c) }
                  : m
              ))
              break
            case 'error':
              setMessages(prev => prev.map(m =>
                m.id === asstId
                  ? { ...m, content: m.content + `\n\n⚠ ${evt.content}`, streaming: false }
                  : m
              ))
              break
            case 'done':
              setMessages(prev => prev.map(m =>
                m.id === asstId ? { ...m, streaming: false } : m
              ))
              break
          }
        }
      }

      fetchConversations()

    } catch (err) {
      if (err.name === 'AbortError') return
      setMessages(prev => prev.map(m =>
        m.id === asstId
          ? { ...m, content: m.content || `Connection error: ${err.message}`, streaming: false }
          : m
      ))
    } finally {
      setIsStreaming(false)
      setMessages(prev => prev.map(m =>
        m.id === asstId ? { ...m, streaming: false } : m
      ))
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isStreaming, threadId, getToken, fetchConversations])

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) }
  }

  const isEmpty = messages.length === 0 && !messagesLoading

  return (
    <div style={{
      display: 'flex', height: '100%',
      background: 'var(--bg)', position: 'relative', overflow: 'hidden',
    }}>
      <ConversationsSidebar
        conversations={conversations}
        convosLoading={convosLoading}
        threadId={threadId}
        onSelect={selectConversation}
        onDelete={deleteConversation}
        onNewThread={newThread}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed(p => !p)}
        isMobile={isMobile}
      />

      {isMobile && !sidebarCollapsed && (
        <div
          onClick={() => setSidebarCollapsed(true)}
          style={{
            position: 'absolute', inset: 0,
            background: 'rgba(0,0,0,0.55)',
            backdropFilter: 'blur(3px)',
            zIndex: 4,
          }}
        />
      )}

      {/* Chat panel */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, position: 'relative' }}>

        {/* Empty state — Claude-style centered greeting */}
        {isEmpty ? (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            padding: isMobile ? '32px 20px' : '60px 40px',
            gap: 0,
          }}>
            {/* Mobile sidebar toggle */}
            {isMobile && (
              <button
                onClick={() => setSidebarCollapsed(p => !p)}
                style={{
                  position: 'absolute', top: 16, left: 16,
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--text-muted)', padding: 4,
                  display: 'flex', alignItems: 'center',
                }}
              >
                <Menu size={20} />
              </button>
            )}

            {/* Greeting */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 36 }}>
              <h1 style={{
                fontFamily: "'Alfa Slab One', serif",
                fontSize: isMobile ? '2rem' : '2.6rem',
                fontWeight: 500,
                color: 'var(--text-primary)',
                margin: 0,
                letterSpacing: '-0.01em',
                lineHeight: 1,
              }}>
                {greeting}, {firstName}
              </h1>
            </div>

            {/* Input area */}
            <div style={{ width: '100%', maxWidth: 680, marginBottom: 24 }}>
              <ChatComposer
                ref={inputRef}
                input={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                onSend={() => sendMessage(input)}
                isStreaming={isStreaming}
                centered
              />
            </div>

            {/* Suggestion pills */}
            <div style={{
              display: 'flex', flexWrap: 'wrap', gap: 8,
              justifyContent: 'center', maxWidth: 640,
            }}>
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  style={{
                    padding: '8px 16px',
                    background: 'var(--card-bg)',
                    border: '1px solid var(--card-border)',
                    borderRadius: 20,
                    color: 'var(--text-secondary)',
                    cursor: 'pointer',
                    fontFamily: "'Knewave', cursive",
                    fontSize: '0.75rem',
                    transition: 'all 0.18s',
                    letterSpacing: '0.01em',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = 'var(--hover-bg)'
                    e.currentTarget.style.color = 'var(--text-primary)'
                    e.currentTarget.style.borderColor = 'rgba(255,255,255,0.16)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = 'var(--card-bg)'
                    e.currentTarget.style.color = 'var(--text-secondary)'
                    e.currentTarget.style.borderColor = 'var(--card-border)'
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* Active chat state */
          <>
            {/* Thin top bar when messages are visible */}
            <div style={{
              padding: isMobile ? '12px 16px' : '14px 24px',
              borderBottom: '1px solid var(--card-border)',
              flexShrink: 0, display: 'flex', alignItems: 'center', gap: 10,
            }}>
              {isMobile && (
                <button
                  onClick={() => setSidebarCollapsed(p => !p)}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--text-muted)', padding: 4,
                    display: 'flex', alignItems: 'center',
                  }}
                >
                  <Menu size={18} />
                </button>
              )}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{
                  fontFamily: "'Alfa Slab One', serif",
                  fontSize: '1rem',
                  fontWeight: 500,
                  color: 'var(--text-primary)',
                  letterSpacing: '0.01em',
                }}>
                  FashionOS Chat
                </span>
              </div>
            </div>

            {/* Messages */}
            <div style={{
              flex: 1, overflowY: 'auto',
              padding: isMobile ? '24px 16px' : '32px 24px',
              display: 'flex', flexDirection: 'column', gap: 28,
            }}>
              {messagesLoading ? (
                <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Loader2 size={20} color="var(--text-muted)"
                    style={{ animation: 'spin 1s linear infinite', opacity: 0.5 }} />
                </div>
              ) : (
                messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Composer fixed at bottom */}
            <ChatComposer
              ref={inputRef}
              input={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              onSend={() => sendMessage(input)}
              isStreaming={isStreaming}
            />
          </>
        )}
      </div>

      <style>{`
        @keyframes spin  { to { transform: rotate(360deg); } }
        @keyframes blink { 0%,100% { opacity:1; } 50% { opacity:0; } }
        @keyframes bounce {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-4px); }
        }
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  )
}