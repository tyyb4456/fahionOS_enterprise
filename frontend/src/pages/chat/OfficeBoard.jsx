// frontend/src/pages/chat/OfficeBoard.jsx
import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Loader2, CheckCircle2, Package, TrendingUp, Megaphone, Landmark, Brain, Headphones, Shirt } from 'lucide-react'

// Real subagent tool names — must match agents/*/graph.py's CompiledSubAgent
// `name=` and deep_agent/runtime.py's `subagents=[...]` list exactly.
// `captions` are purely decorative flavor text cycled client-side while
// status === 'working' — they are NOT tied to real build_context/reason/
// extract_decision/persist node transitions. Real per-node granularity
// needs backend instrumentation (astream_events + subgraphs=True) — a
// separate v3 piece, not part of this component.
const AGENT_CONFIG = {
  inventory_agent: {
    label: 'Inventory', Icon: Package, color: '#22c55e',
    captions: ['Checking stock levels…', 'Reviewing suppliers…', 'Running forecasts…'],
  },
  sales_agent: {
    label: 'Sales', Icon: TrendingUp, color: '#60a5fa',
    captions: ['Crunching revenue…', 'Reviewing orders…', 'Spotting trends…'],
  },
  marketing_agent: {
    label: 'Marketing', Icon: Megaphone, color: '#f97316',
    captions: ['Drafting copy…', 'Checking ad spend…', 'Planning content…'],
  },
  finance_agent: {
    label: 'Finance', Icon: Landmark, color: '#facc15',
    captions: ['Reviewing the books…', 'Checking cash flow…', 'Running the numbers…'],
  },
  research_agent: {
    label: 'Research', Icon: Brain, color: '#a855f7',
    captions: ['Analyzing data…', 'Reading reports…', 'Exploring insights…'],
  },
  supplier_agent: {
    label: 'Supplier', Icon: Package, color: '#38bdf8',
    captions: ['Contacting suppliers…', 'Negotiating terms…', 'Tracking shipments…'],
  },
  product_agent: {
    label: 'Product', Icon: Shirt, color: '#f472b6',
    captions: ['Reviewing the catalog…', 'Planning collections…', 'Scoring opportunities…'],
  },
  customer_support_agent: {
    label: 'Support', Icon: Headphones, color: '#e879f9',
    captions: ['Answering tickets…', 'Resolving conversations…', 'Checking feedback…'],
  },
}

const AGENT_ORDER = ['inventory_agent', 'sales_agent', 'marketing_agent', 'finance_agent', 'research_agent', 'supplier_agent', 'customer_support_agent', 'product_agent']
// x position (% of stage width) each agent's desk sits at
const X_POS = { research_agent: 5, sales_agent: 16, supplier_agent: 27, inventory_agent: 38, marketing_agent: 62, finance_agent: 73, product_agent: 84, customer_support_agent: 95 }

const DONE_LINGER_MS = 4000
const CAPTION_CYCLE_MS = 1900

function deriveAgentStatuses(toolCalls) {
  const statuses = {}
  for (const call of toolCalls || []) {
    const baseName = call.name?.split('#')[0]
    if (!AGENT_CONFIG[baseName]) continue // skip get_pipeline_status, start_agent_analysis, etc.
    statuses[baseName] = call.status === 'running' ? 'working' : 'done'
  }
  return statuses
}

function TaskPacket({ fromX, toX, toY, color }) {
  return (
    <motion.div
      initial={{ left: `${fromX}%`, top: 14, opacity: 0, scale: 0.4 }}
      animate={{ left: `${toX}%`, top: toY, opacity: [0, 1, 1, 0], scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.6, ease: 'easeInOut' }}
      style={{
        position: 'absolute', width: 8, height: 8, borderRadius: '50%',
        background: color, x: '-50%', boxShadow: `0 0 6px ${color}`,
      }}
    />
  )
}

function AgentAvatar({ agentKey, status, xPercent, deskY, loungeY, isMobile }) {
  const { label, Icon, color, captions } = AGENT_CONFIG[agentKey]
  const atDesk = status === 'working' || status === 'done'
  const [captionIdx, setCaptionIdx] = useState(0)

  useEffect(() => {
    if (status !== 'working') return
    const id = setInterval(() => setCaptionIdx(i => (i + 1) % captions.length), CAPTION_CYCLE_MS)
    return () => clearInterval(id)
  }, [status, captions.length])

  return (
    <motion.div
      style={{ position: 'absolute', left: `${xPercent}%`, x: '-50%', zIndex: atDesk ? 3 : 2 }}
      animate={{ top: atDesk ? deskY : loungeY }}
      transition={{ type: 'spring', stiffness: 140, damping: 18 }}
    >
      {/* Caption bubble while working */}
      <AnimatePresence mode="wait">
        {status === 'working' && (
          <motion.div
            key={captionIdx}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.25 }}
            style={{
              position: 'absolute', bottom: '100%', left: '50%', x: '-50%',
              marginBottom: 6, whiteSpace: 'nowrap',
              background: 'var(--card-bg)', border: `1px solid ${color}55`,
              color, fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: '0.55rem',
              padding: '3px 8px', borderRadius: 8,
            }}
          >
            {captions[captionIdx]}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Idle/working micro-motion — separate from the walk animation above */}
      <motion.div
        animate={atDesk ? { y: [0, -1, 0] } : { y: [0, -3, 0] }}
        transition={{ duration: atDesk ? 1.6 : 2.6, repeat: Infinity, ease: 'easeInOut' }}
        style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}
      >
        <div style={{
          position: 'relative',
          width: isMobile ? 34 : 42, height: isMobile ? 34 : 42, borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: atDesk ? `${color}22` : 'var(--item-bg)',
          border: `1.5px solid ${atDesk ? color : 'var(--item-border)'}`,
          boxShadow: status === 'working' ? `0 0 0 5px ${color}14` : 'none',
          transition: 'background 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease',
        }}>
          <Icon size={isMobile ? 15 : 18} color={atDesk ? color : 'var(--text-muted)'} style={{ opacity: atDesk ? 1 : 0.6 }} />

          {status === 'working' && (
            <div style={{
              position: 'absolute', top: -3, right: -3, width: 14, height: 14, borderRadius: '50%',
              background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Loader2 size={9} color={color} style={{ animation: 'officeboard-spin 0.9s linear infinite' }} />
            </div>
          )}
          {status === 'done' && (
            <motion.div
              initial={{ scale: 0 }} animate={{ scale: 1 }}
              transition={{ type: 'spring', stiffness: 300, damping: 12 }}
              style={{
                position: 'absolute', top: -3, right: -3, width: 14, height: 14, borderRadius: '50%',
                background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <CheckCircle2 size={11} color="#22c55e" />
            </motion.div>
          )}
        </div>

        <span style={{
          fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: isMobile ? '0.5rem' : '0.56rem',
          letterSpacing: '0.04em', textTransform: 'uppercase',
          color: atDesk ? color : 'var(--text-muted)', opacity: atDesk ? 1 : 0.65,
          whiteSpace: 'nowrap',
        }}>
          {label}
        </span>
      </motion.div>
    </motion.div>
  )
}

export default function OfficeBoard({ toolCalls, isStreaming, isMobile = false }) {
  const [statuses, setStatuses] = useState({})
  const [packets, setPackets] = useState([])
  const timersRef = useRef({})
  const prevStatusesRef = useRef({})

  useEffect(() => {
    const latest = deriveAgentStatuses(toolCalls)
    if (Object.keys(latest).length === 0) return

    const prevSnapshot = prevStatusesRef.current
    const merged = { ...prevSnapshot, ...latest }

    // idle/undefined -> working transitions get a task-packet flight
    const newPackets = []
    for (const [agentKey, status] of Object.entries(latest)) {
      const was = prevSnapshot[agentKey]
      if (status === 'working' && was !== 'working' && was !== 'done') {
        newPackets.push({ id: `${agentKey}-${Date.now()}`, agentKey })
      }
    }

    prevStatusesRef.current = merged
    setStatuses(merged)

    if (newPackets.length) {
      setPackets(p => [...p, ...newPackets])
      newPackets.forEach(pk => {
        setTimeout(() => setPackets(p => p.filter(x => x.id !== pk.id)), 650)
      })
    }

    for (const [agentKey, status] of Object.entries(latest)) {
      if (status !== 'done') continue
      clearTimeout(timersRef.current[agentKey])
      timersRef.current[agentKey] = setTimeout(() => {
        setStatuses(prev => {
          if (prev[agentKey] !== 'done') return prev
          const next = { ...prev, [agentKey]: 'idle' }
          prevStatusesRef.current = next
          return next
        })
      }, DONE_LINGER_MS)
    }
  }, [toolCalls])

  // New turn starting with no tool calls yet — clear any lingering glow.
  useEffect(() => {
    if (isStreaming && (!toolCalls || toolCalls.length === 0)) {
      Object.values(timersRef.current).forEach(clearTimeout)
      timersRef.current = {}
      prevStatusesRef.current = {}
      /* eslint-disable react-hooks/set-state-in-effect */
      setStatuses({})
      setPackets([])
      /* eslint-enable react-hooks/set-state-in-effect */
    }
  }, [isStreaming, toolCalls])

  useEffect(() => () => Object.values(timersRef.current).forEach(clearTimeout), [])

  const anyActive = Object.values(statuses).some(s => s === 'working' || s === 'done')
  const STAGE_H = isMobile ? 176 : 220
  const DESK_Y = isMobile ? 42 : 54
  const LOUNGE_Y = STAGE_H - (isMobile ? 36 : 46)
  const SUPERVISOR_Y = isMobile ? 4 : 8

  return (
    <div style={{
      position: 'relative', height: STAGE_H, overflow: 'hidden',
      background: 'var(--card-bg)', border: '1px solid var(--card-border)', borderRadius: 12,
      padding: '0 4px',
    }}>
      <style>{`@keyframes officeboard-spin { to { transform: rotate(360deg); } }`}</style>

      {/* Supervisor */}
      <motion.div
        style={{
          position: 'absolute', left: '50%', x: '-50%', top: SUPERVISOR_Y, zIndex: 2,
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
        }}
        animate={{ scale: anyActive ? 1.05 : 1 }}
        transition={{ duration: 0.3 }}
      >
        <div style={{
          width: isMobile ? 34 : 42, height: isMobile ? 34 : 42, borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: anyActive ? 'rgba(212,212,216,0.16)' : 'var(--item-bg)',
          border: `1.5px solid ${anyActive ? 'var(--gold)' : 'var(--item-border)'}`,
          transition: 'background 0.3s ease, border-color 0.3s ease',
        }}>
          <Brain size={isMobile ? 15 : 18} color={anyActive ? 'var(--gold)' : 'var(--text-muted)'} />
        </div>
        <span style={{
          fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: isMobile ? '0.5rem' : '0.56rem',
          letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--text-muted)',
        }}>
          Supervisor
        </span>
      </motion.div>

      {/* Static desk surfaces — lit when occupied */}
      {AGENT_ORDER.map(agentKey => {
        const { color } = AGENT_CONFIG[agentKey]
        const status = statuses[agentKey] || 'idle'
        const occupied = status === 'working' || status === 'done'
        return (
          <div key={`desk-${agentKey}`} style={{
            position: 'absolute', left: `${X_POS[agentKey]}%`, transform: 'translateX(-50%)',
            top: DESK_Y + (isMobile ? 20 : 26),
            width: isMobile ? 30 : 38, height: isMobile ? 6 : 8, borderRadius: 3,
            background: occupied ? `${color}55` : 'var(--item-border)',
            transition: 'background 0.3s ease',
          }} />
        )
      })}

      {/* Task packets — Supervisor delegating */}
      <AnimatePresence>
        {packets.map(p => (
          <TaskPacket
            key={p.id}
            fromX={50}
            toX={X_POS[p.agentKey]}
            toY={DESK_Y}
            color={AGENT_CONFIG[p.agentKey].color}
          />
        ))}
      </AnimatePresence>

      {/* Agent avatars */}
      {AGENT_ORDER.map(agentKey => (
        <AgentAvatar
          key={agentKey}
          agentKey={agentKey}
          status={statuses[agentKey] || 'idle'}
          xPercent={X_POS[agentKey]}
          deskY={DESK_Y}
          loungeY={LOUNGE_Y}
          isMobile={isMobile}
        />
      ))}

      <div style={{
        position: 'absolute', left: 8, top: LOUNGE_Y - (isMobile ? 14 : 18),
        fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: '0.5rem', letterSpacing: '0.08em',
        textTransform: 'uppercase', color: 'var(--text-muted)', opacity: 0.4,
      }}>
        Break room
      </div>
    </div>
  )
}