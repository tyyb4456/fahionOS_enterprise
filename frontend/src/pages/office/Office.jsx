// frontend/src/pages/office/Office.jsx
// Virtual AI Office — a live 3D workspace showing the real FashionOS agent
// system. CEO/supervisor desk at the back, six employee desks in two rows,
// real agent status/actions from /api/v1/office/stream, animated inter-agent
// communication, notifications and an activity feed.
import { Component, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { Bell, X, RotateCcw, Loader2, WifiOff, MessageSquare, ArrowDownRight, ArrowUpLeft, ChevronLeft, Building2, Activity, Inbox } from 'lucide-react'
import { useOfficeFeed } from './useOfficeFeed'
import Office3D from './Office3D'
import { AGENT_ORDER, agentMeta, SUPERVISOR, STATUS_LABEL } from './config'
import { sourceMeta } from '../chat/constants'

const GOLD = 'var(--gold)'

function fmtTime(ts) {
  if (!ts) return ''
  try { return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) } catch { return '' }
}

const STATUS_COLOR = { idle: '#8a8a92', working: GOLD, done: '#22c55e', error: '#ef4444' }

function eventSummary(evt) {
  switch (evt.type) {
    case 'run.start': return 'Run started'
    case 'run.end': return 'Run finished'
    case 'supervisor.status': return `Supervisor ${evt.status}`
    case 'agent.status': {
      const meta = sourceMeta(evt.agent)
      return `${meta.label} ${evt.status}${evt.action ? ` — ${evt.action}` : ''}`
    }
    case 'agent.tool': {
      const meta = sourceMeta(evt.agent)
      return `${meta.label} → ${evt.tool}`
    }
    case 'agent.message': {
      const from = evt.from === 'supervisor' ? 'Supervisor' : sourceMeta(evt.from).label
      const to = evt.to === 'supervisor' ? 'Supervisor' : sourceMeta(evt.to).label
      return `${from} → ${to}: ${evt.text}`
    }
    default: return evt.type || ''
  }
}

// Canvas can throw if WebGL is unavailable — keep the rest of the page usable.
class CanvasBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) {
      return (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, color: 'var(--text-muted)', textAlign: 'center', padding: 24 }}>
          <Building2 size={36} style={{ color: 'var(--gold)' }} />
          <div style={{ fontFamily: "'Knewave', cursive", letterSpacing: '0.06em' }}>3D office unavailable</div>
          <div style={{ fontSize: '0.8rem', maxWidth: 380, lineHeight: 1.5 }}>
            Your browser can&apos;t open a WebGL scene here. The live feed below still works.
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function StatusPill({ status, text }) {
  const color = STATUS_COLOR[status] || GOLD
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '2px 9px', borderRadius: 999,
      background: 'var(--item-bg)', border: `1px solid ${color}44`,
      color, fontFamily: "'Knewave', cursive", fontSize: '0.62rem', letterSpacing: '0.06em',
      textTransform: 'uppercase', whiteSpace: 'nowrap',
    }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}` }} />
      {text}
    </span>
  )
}

function ConnectionPill({ connected, connecting, error }) {
  if (error) return <StatusPill status="error" text="Offline" />
  if (connecting) return <StatusPill status="working" text="Connecting…" />
  if (connected) return <StatusPill status="done" text="Live" />
  return <StatusPill status="idle" text="Reconnecting…" />
}

function NotificationItem({ n }) {
  const agent = n.agent === 'supervisor' ? SUPERVISOR : agentMeta(n.agent)
  const color = n.agent === 'supervisor' ? GOLD : agent.color
  const icon = n.kind === 'error' ? '⚠' : n.kind === 'done' ? '✓' : '→'
  return (
    <div style={{ display: 'flex', gap: 10, padding: '8px 12px', alignItems: 'flex-start', borderBottom: '1px solid var(--card-border)' }}>
      <span style={{
        width: 24, height: 24, borderRadius: '50%', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: `${color}1e`, border: `1px solid ${color}55`, color, fontSize: '0.7rem',
      }}>
        {icon}
      </span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: '0.74rem', color: 'var(--text-primary)', fontFamily: "'Knewave', cursive", letterSpacing: '0.02em' }}>
          {n.agent === 'supervisor' ? 'Supervisor' : agent.label}
        </div>
        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.text}</div>
      </div>
      <span style={{ marginLeft: 'auto', fontSize: '0.6rem', color: 'var(--text-muted)', flexShrink: 0 }}>{fmtTime(n.ts)}</span>
    </div>
  )
}

function CommunicationFeed({ messages }) {
  if (messages.length === 0) {
    return (
      <div style={{ padding: '18px 14px', color: 'var(--text-muted)', fontSize: '0.74rem', textAlign: 'center', lineHeight: 1.6 }}>
        No inter-agent messages yet. Start a conversation in <b>Chat</b> and watch the supervisor delegate tasks in real time.
      </div>
    )
  }
  return (
    <div>
      {messages.map(m => {
        const isTask = m.kind === 'task'
        const sender = m.from === 'supervisor' ? SUPERVISOR : agentMeta(m.from)
        const receiver = m.to === 'supervisor' ? SUPERVISOR : agentMeta(m.to)
        const color = isTask ? GOLD : (sender.color || GOLD)
        const Arrow = isTask ? ArrowDownRight : ArrowUpLeft
        return (
          <div key={m.id} style={{ display: 'flex', gap: 10, padding: '9px 14px', alignItems: 'center', borderBottom: '1px solid var(--card-border)' }}>
            <span style={{
              width: 26, height: 26, borderRadius: 8, flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: `${color}1a`, border: `1px solid ${color}44`, color,
            }}>
              <Arrow size={13} />
            </span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', fontFamily: "'Knewave', cursive", letterSpacing: '0.04em' }}>
                {sender.label} → {receiver.label}
              </div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-primary)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.text}</div>
            </div>
            <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', flexShrink: 0 }}>{fmtTime(m.ts)}</span>
          </div>
        )
      })}
    </div>
  )
}

function EventLog({ activity }) {
  return (
    <div>
      {activity.map((e, i) => (
        <div key={i} style={{ display: 'flex', gap: 10, padding: '6px 14px', alignItems: 'center' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: e.type === 'run.start' ? GOLD : e.type === 'agent.tool' ? '#60a5fa' : '#5a5a62', flexShrink: 0 }} />
          <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{eventSummary(e)}</span>
          <span style={{ fontSize: '0.58rem', color: 'var(--text-muted)', flexShrink: 0 }}>{fmtTime(e.ts)}</span>
        </div>
      ))}
      {activity.length === 0 && (
        <div style={{ padding: '16px 14px', color: 'var(--text-muted)', fontSize: '0.72rem', textAlign: 'center' }}>No recent activity.</div>
      )}
    </div>
  )
}

export default function Office() {
  const { getToken } = useAuth()
  const feed = useOfficeFeed({ getToken, enabled: true })
  const [selected, setSelected] = useState(null)
  const [showFeed, setShowFeed] = useState(false)
  const [showNotifs, setShowNotifs] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const sceneRef = useRef(null)

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 768)
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const unreadByAgent = useMemo(() => {
    const m = {}
    for (const n of feed.notifications) m[n.agent] = (m[n.agent] || 0) + 1
    return m
  }, [feed.notifications])

  const agents = useMemo(() => {
    const next = {}
    for (const key of AGENT_ORDER) next[key] = { ...feed.agents[key], unread: unreadByAgent[key] || 0 }
    return next
  }, [feed.agents, unreadByAgent])

  const supervisor = { ...feed.supervisor, unread: unreadByAgent.supervisor || 0 }

  const handleSelect = (key) => {
    setSelected(key)
    feed.markRead(key)
    setShowFeed(false)
  }
  const handleClose = () => setSelected(null)

  const anyBusy = supervisor.status !== 'idle' || Object.values(feed.agents).some(a => a.status !== 'idle')
  const allIdle = feed.connected && !anyBusy && feed.messages.length === 0 && feed.activity.length === 0

  const selectedMeta = selected === 'supervisor' ? SUPERVISOR : (selected ? agentMeta(selected) : null)
  const selectedNotifications = selected ? feed.notifications.filter(n => n.agent === selected) : []
  const selectedStatus = selected === 'supervisor' ? supervisor.status : (selected ? feed.agents[selected]?.status : 'idle')
  const selectedAction = selected === 'supervisor' ? supervisor.action : (selected ? feed.agents[selected]?.action : '')
  const selectedNode = selected ? feed.agents[selected]?.node : ''
  const selectedTool = selected ? feed.agents[selected]?.lastTool : ''

  const panel = (
    <div style={{
      width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column',
      background: 'var(--card-bg)', borderLeft: '1px solid var(--card-border)',
      height: '100%', overflowY: 'auto',
    }}>
      {selected ? (
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderBottom: '1px solid var(--card-border)' }}>
            <button onClick={handleClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex' }}>
              <ChevronLeft size={16} />
            </button>
            <span style={{ fontFamily: "'Knewave', cursive", fontSize: '0.72rem', letterSpacing: '0.08em', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Back to feed
            </span>
          </div>
          <div style={{ padding: '16px 16px', borderBottom: '1px solid var(--card-border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{
                width: 46, height: 46, borderRadius: '50%', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: `${selectedMeta.color}1a`, border: `1.5px solid ${selectedMeta.color}`,
                fontFamily: "'Alfa Slab One', serif", color: selectedMeta.color, fontSize: '1rem',
              }}>
                {selectedMeta.label.slice(0, 1)}
              </div>
              <div>
                <div style={{ fontFamily: "'Alfa Slab One', serif", fontSize: '0.95rem', letterSpacing: '0.06em', color: 'var(--text-primary)' }}>{selectedMeta.label}</div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 1 }}>{selectedMeta.role}</div>
              </div>
            </div>
          </div>
          <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Status</span>
              <StatusPill status={selectedStatus} text={STATUS_LABEL[selectedStatus] || selectedStatus} />
            </div>
            {selectedAction && (
              <div style={{ fontSize: '0.76rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                <span style={{ color: selectedMeta.color }}>{selectedAction}</span>
                {selectedNode ? <span style={{ color: 'var(--text-muted)' }}> · {selectedNode}</span> : null}
              </div>
            )}
            {selectedTool && (
              <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                last tool: <span style={{ color: 'var(--gold)', fontFamily: 'monospace' }}>{selectedTool}</span>
              </div>
            )}
            {selectedNotifications.length > 0 && (
              <div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                  Notifications
                </div>
                {selectedNotifications.map(n => <NotificationItem key={n.id} n={n} />)}
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--card-border)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <MessageSquare size={14} style={{ color: 'var(--gold)' }} />
            <span style={{ fontFamily: "'Knewave', cursive", fontSize: '0.72rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-primary)' }}>Communication</span>
          </div>
          <CommunicationFeed messages={feed.messages} />
          <div style={{ padding: '12px 14px', borderTop: '1px solid var(--card-border)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Activity size={14} style={{ color: 'var(--gold)' }} />
            <span style={{ fontFamily: "'Knewave', cursive", fontSize: '0.72rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-primary)' }}>Recent activity</span>
          </div>
          <EventLog activity={feed.activity} />
        </>
      )}
    </div>
  )

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg)', minHeight: 0 }}>
      <style>{`@keyframes office-slide { 0% { transform: translateX(-100%);} 100% { transform: translateX(220%);} }
        @keyframes office-pulse { 0%,100% { opacity: 1;} 50% { opacity: 0.35;} }`}</style>

      {/* Header */}
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        padding: '10px 16px', flexShrink: 0,
        background: 'var(--card-bg)', borderBottom: '1px solid var(--card-border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <Building2 size={18} style={{ color: 'var(--gold)', flexShrink: 0 }} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: "'Alfa Slab One', serif", fontSize: '1rem', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
              Virtual AI Office
            </div>
            <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', fontFamily: "'Knewave', cursive", letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
              Live agent workspace · drag to look around
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <ConnectionPill connected={feed.connected} connecting={feed.connecting} error={feed.error} />

          <button onClick={() => sceneRef.current?.resetView()}
            title="Reset camera"
            style={iconBtn}>
            <RotateCcw size={14} />
          </button>

          <div style={{ position: 'relative' }}>
            <button onClick={() => setShowNotifs(v => !v)} title="Notifications" style={iconBtn}>
              <Bell size={14} />
              {supervisor.unread > 0 && (
                <span style={{
                  position: 'absolute', top: -4, right: -4, minWidth: 15, height: 15, borderRadius: 8,
                  padding: '0 3px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: '#ef4444', color: '#fff', fontSize: '0.56rem', fontWeight: 700,
                }}>
                  {supervisor.unread}
                </span>
              )}
            </button>
            {showNotifs && (
              <>
                <div style={{ position: 'fixed', inset: 0, zIndex: 20 }} onClick={() => setShowNotifs(false)} />
                <div style={{
                  position: 'absolute', right: 0, top: 34, zIndex: 30, width: 260,
                  background: 'var(--card-bg)', border: '1px solid var(--card-border)', borderRadius: 12,
                  boxShadow: '0 12px 40px rgba(0,0,0,0.55)', overflow: 'hidden',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', borderBottom: '1px solid var(--card-border)' }}>
                    <span style={{ fontFamily: "'Knewave', cursive", fontSize: '0.7rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-primary)' }}>Notifications</span>
                    <button onClick={feed.markAllRead} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gold)', fontSize: '0.65rem', fontFamily: "'Knewave', cursive" }}>
                      Clear all
                    </button>
                  </div>
                  <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                    {feed.notifications.length === 0
                      ? <div style={{ padding: 16, fontSize: '0.72rem', color: 'var(--text-muted)', textAlign: 'center' }}>No notifications yet.</div>
                      : feed.notifications.map(n => <NotificationItem key={n.id} n={n} />)}
                  </div>
                </div>
              </>
            )}
          </div>

          {isMobile && (
            <button onClick={() => { setShowFeed(v => !v); setSelected(null) }} title="Activity feed" style={iconBtn}>
              <Inbox size={14} />
            </button>
          )}
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        {/* 3D canvas */}
        <div className="relative flex-1 min-w-0" style={{ minHeight: 0 }}>
          <CanvasBoundary>
            <Office3D
              ref={sceneRef}
              agents={agents}
              supervisor={supervisor}
              packets={feed.packets}
              selected={selected}
              onSelect={handleSelect}
              isMobile={isMobile}
            />
          </CanvasBoundary>

          {/* Loading overlay */}
          {(feed.connecting || (!feed.connected && !feed.error)) && !allIdle && (
            <div style={overlayStyle}>
              <Loader2 size={22} style={{ color: 'var(--gold)', animation: 'office-pulse 1.2s ease-in-out infinite' }} />
              <span style={{ fontFamily: "'Knewave', cursive", fontSize: '0.72rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                Connecting to the office…
              </span>
            </div>
          )}

          {/* Disconnected banner */}
          {feed.error && (
            <div style={{
              position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)', zIndex: 15,
              display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
              background: 'var(--card-bg)', border: '1px solid #ef444466', borderRadius: 10,
            }}>
              <WifiOff size={14} style={{ color: '#ef4444' }} />
              <span style={{ fontSize: '0.72rem', color: 'var(--text-primary)' }}>Live feed unavailable</span>
              <button onClick={feed.retryNow} style={{
                background: 'var(--hover-bg)', border: '1px solid var(--card-border)', borderRadius: 8,
                padding: '3px 10px', cursor: 'pointer', color: 'var(--gold)', fontFamily: "'Knewave', cursive", fontSize: '0.66rem',
              }}>
                Retry
              </button>
            </div>
          )}

          {/* Connected indicator chip */}
          {feed.connected && (
            <div style={{
              position: 'absolute', top: 12, left: 12, zIndex: 15, display: 'flex', alignItems: 'center', gap: 6,
              padding: '4px 10px', borderRadius: 999, background: 'rgba(18,18,20,0.8)',
              border: '1px solid #22c55e44', color: '#22c55e', fontSize: '0.6rem',
              fontFamily: "'Knewave', cursive", letterSpacing: '0.06em',
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e', animation: 'office-pulse 2s ease-in-out infinite' }} />
              LIVE
            </div>
          )}

          {/* Idle hint */}
          {allIdle && (
            <div style={{
              position: 'absolute', bottom: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 15,
              padding: '8px 14px', borderRadius: 10, background: 'rgba(18,18,20,0.82)',
              border: '1px solid var(--card-border)', color: 'var(--text-muted)',
              fontSize: '0.72rem', textAlign: 'center', maxWidth: 420, lineHeight: 1.5,
            }}>
              Agents are online and standing by. Start a conversation in <b style={{ color: 'var(--gold)' }}>Chat</b> and watch them work.
            </div>
          )}
        </div>

        {/* Desktop side panel */}
        {!isMobile && panel}

        {/* Mobile: activity feed overlay */}
        {isMobile && showFeed && (
          <div style={{
            position: 'fixed', inset: 0, zIndex: 40, display: 'flex', flexDirection: 'column',
            background: 'var(--bg)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderBottom: '1px solid var(--card-border)' }}>
              <span style={{ fontFamily: "'Alfa Slab One', serif", fontSize: '0.95rem', letterSpacing: '0.06em', color: 'var(--text-primary)' }}>Activity</span>
              <button onClick={() => setShowFeed(false)} style={iconBtn}><X size={16} /></button>
            </div>
            <div style={{ overflowY: 'auto', flex: 1 }}>
              <CommunicationFeed messages={feed.messages} />
              <EventLog activity={feed.activity} />
            </div>
          </div>
        )}

        {/* Mobile: detail bottom sheet */}
        {isMobile && selected && selectedMeta && (
          <div style={{
            position: 'fixed', inset: 0, zIndex: 40, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
            background: 'rgba(0,0,0,0.55)',
          }} onClick={handleClose}>
            <div style={{
              background: 'var(--card-bg)', borderTop: '1px solid var(--card-border)',
              borderTopLeftRadius: 16, borderTopRightRadius: 16, maxHeight: '75%', overflowY: 'auto',
            }} onClick={e => e.stopPropagation()}>
              <div style={{ padding: '16px 16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 44, height: 44, borderRadius: '50%', flexShrink: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: `${selectedMeta.color}1a`, border: `1.5px solid ${selectedMeta.color}`,
                    fontFamily: "'Alfa Slab One', serif", color: selectedMeta.color, fontSize: '1rem',
                  }}>
                    {selectedMeta.label.slice(0, 1)}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: "'Alfa Slab One', serif", fontSize: '0.95rem', letterSpacing: '0.06em', color: 'var(--text-primary)' }}>{selectedMeta.label}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 1 }}>{selectedMeta.role}</div>
                  </div>
                  <StatusPill status={selectedStatus} text={STATUS_LABEL[selectedStatus] || selectedStatus} />
                </div>
                {selectedAction && (
                  <div style={{ marginTop: 14, fontSize: '0.78rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                    <span style={{ color: selectedMeta.color }}>{selectedAction}</span>
                    {selectedNode ? <span style={{ color: 'var(--text-muted)' }}> · {selectedNode}</span> : null}
                  </div>
                )}
                {selectedTool && (
                  <div style={{ marginTop: 8, fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                    last tool: <span style={{ color: 'var(--gold)', fontFamily: 'monospace' }}>{selectedTool}</span>
                  </div>
                )}
                {selectedNotifications.length > 0 && (
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>Notifications</div>
                    {selectedNotifications.map(n => <NotificationItem key={n.id} n={n} />)}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const iconBtn = {
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  width: 30, height: 30, borderRadius: 8, flexShrink: 0,
  background: 'var(--hover-bg)', border: '1px solid var(--card-border)',
  color: 'var(--text-secondary)', cursor: 'pointer', position: 'relative',
}

const overlayStyle = {
  position: 'absolute', inset: 0, zIndex: 14,
  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10,
  background: 'rgba(13,13,15,0.7)', backdropFilter: 'blur(2px)',
}
