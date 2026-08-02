import { KEY_LABEL_OVERRIDES } from './constants'

// ── IDs ──────────────────────────────────────────────────────────────────────────
export const uuidv4 = () => crypto.randomUUID()

// ── Relative time helper ─────────────────────────────────────────────────────────
export function relativeTime(iso) {
  if (!iso) return ''
  const diff  = Date.now() - new Date(iso).getTime()
  const mins  = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days  = Math.floor(diff / 86400000)
  if (mins  <  1) return 'just now'
  if (mins  < 60) return `${mins}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days  <  7) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

// ── Small uppercase pill badge ───────────────────────────────────────────────────
export function badge(text, color) {
  return (
    <span style={{
      fontFamily: "'Knewave', cursive",
      fontSize: '0.52rem', letterSpacing: '0.12em',
      textTransform: 'uppercase', padding: '2px 6px',
      border: `1px solid ${color}55`, color,
      background: `${color}14`, display: 'inline-block',
    }}>{text}</span>
  )
}

// ── Thin horizontal divider ───────────────────────────────────────────────────────
export function Divider({ color = 'rgba(255,255,255,0.07)' }) {
  return <div style={{ height: 1, background: color, margin: '8px 0' }} />
}

// ── PrettyJSON helpers ────────────────────────────────────────────────────────────
export function labelize(key) {
  if (KEY_LABEL_OVERRIDES[key]) return KEY_LABEL_OVERRIDES[key]
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export function formatPrimitive(val) {
  if (val === null || val === undefined || val === '') {
    return <span style={{ color: 'rgba(242,237,228,0.25)' }}>—</span>
  }
  if (typeof val === 'boolean') {
    return badge(val ? 'yes' : 'no', val ? '#22c55e' : 'rgba(242,237,228,0.4)')
  }
  if (typeof val === 'number') {
    return <span style={{ color: '#F2EDE4' }}>{Number.isInteger(val) ? val.toLocaleString() : val}</span>
  }
  if (typeof val === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(val)) {
    try { return <span style={{ color: 'rgba(242,237,228,0.6)' }}>{new Date(val).toLocaleString()}</span> }
    catch { /* fall through */ }
  }
  return <span style={{ color: 'rgba(242,237,228,0.75)' }}>{String(val)}</span>
}

export function isFlatObject(obj) {
  return obj && typeof obj === 'object' && !Array.isArray(obj) &&
    Object.values(obj).every(v => v === null || typeof v !== 'object')
}