import { useState } from 'react'

const MONEY_KEYS = new Set([
  'total_price', 'price', 'total_cost', 'unit_price', 'revenue', 'predicted_revenue',
  'cash_today', 'predicted_cash', 'predicted_expenses', 'expenses', 'profit', 'amount',
  'related_amount', 'current_budget', 'recommended_budget', 'our_price', 'competitor_price',
  'recommended_price', 'initial_offer', 'counter_offer', 'final_price', 'margin',
  'total_spent', 'budget', 'refund_amount', 'total_discount', 'cost_price',
])

const DATE_TIME_KEYS = new Set([
  'created_at', 'updated_at', 'started_at', 'last_message_at', 'recorded_at',
  'incurred_at', 'scheduled_for', 'forecast_date',
])

const DATE_KEYS = new Set(['expected_delivery', 'week_start', 'start_date', 'end_date', 'valid_until'])

const BADGE_KEYS = new Set([
  'status', 'severity', 'priority', 'urgency', 'sentiment', 'result', 'resolved', 'type',
])

const BADGE_TONE = {
  critical: '#ef4444', high: '#f97316', failed: '#ef4444', error: '#ef4444',
  unresolved: '#ef4444', open: '#ef4444',
  warning: '#facc15', medium: '#facc15', refunded: '#facc15', escalated: '#f97316',
  low: '#60a5fa', info: '#60a5fa', proposed: '#60a5fa', scheduled: '#60a5fa', estimated: '#94a3b8',
  draft: '#94a3b8', pending: '#d4d4d8', pending_approval: '#d4d4d8', manufacturing: '#facc15',
  shipped: '#60a5fa', in_transit: '#60a5fa',
  healthy: '#4ade80', done: '#4ade80', completed: '#4ade80', success: '#4ade80',
  active: '#4ade80', connected: '#4ade80', resolved: '#4ade80', paid: '#4ade80',
  posted: '#4ade80', published: '#4ade80', received: '#4ade80', delivered: '#4ade80',
  closed: '#4ade80', positive: '#4ade80',
  negative: '#f87171', return_reason: '#f87171',
}

function badgeTone(key, value) {
  const v = String(value ?? '').toLowerCase().replace(/[^a-z_]/g, '')
  if (key === 'resolved') return value ? '#4ade80' : '#ef4444'
  if (BADGE_TONE[v]) return BADGE_TONE[v]
  return 'var(--gold)'
}

function fmtDateTime(iso) {
  try { return new Date(iso).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) } catch { return iso }
}
function fmtDate(iso) {
  try { return new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' }) } catch { return iso }
}

function formatValue(value, key) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') {
    if (MONEY_KEYS.has(key)) return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '[]'
    if (value.every(v => typeof v === 'string' || typeof v === 'number')) {
      const s = value.join(', ')
      return s.length > 60 ? s.slice(0, 60) + '…' : s
    }
    const s = JSON.stringify(value)
    return s.length > 60 ? s.slice(0, 60) + '…' : s
  }
  if (typeof value === 'object') {
    const s = JSON.stringify(value)
    return s.length > 70 ? s.slice(0, 70) + '…' : s
  }
  if (DATE_TIME_KEYS.has(key)) return fmtDateTime(value)
  if (DATE_KEYS.has(key)) return fmtDate(value)
  const s = String(value)
  return s.length > 80 ? s.slice(0, 80) + '…' : s
}

function cellStyle(key, value) {
  if (BADGE_KEYS.has(key) && typeof value !== 'object' && !Array.isArray(value)) {
    const c = badgeTone(key, value)
    return {
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '1px 8px', borderRadius: 999,
      background: `${c}1a`, border: `1px solid ${c}44`, color: c,
      fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap',
    }
  }
  return {}
}

export default function DataTable({ rows, color = 'var(--gold)' }) {
  const [expanded, setExpanded] = useState(null)

  if (!Array.isArray(rows) || rows.length === 0) return null

  // Union of keys across all rows, preserving first-seen order.
  const columns = []
  for (const r of rows) for (const k of Object.keys(r)) if (!columns.includes(k)) columns.push(k)

  // Prefer non-id-derived columns; keep at most 7 to avoid overflow.
  const shown = columns.filter(k => k !== 'id' && !k.endsWith('_id')).slice(0, 6)
  const extraKeys = columns.slice(0, 12).filter(k => !shown.includes(k))

  const toggleExpand = (idx) => setExpanded(expanded === idx ? null : idx)

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.72rem' }}>
        <thead>
          <tr>
            {shown.map(k => (
              <th key={k} style={{
                textAlign: 'left', padding: '7px 10px', fontSize: '0.6rem',
                color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em',
                borderBottom: '1px solid var(--card-border)', whiteSpace: 'nowrap',
                fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif",
              }}>
                {k.replace(/_/g, ' ')}
              </th>
            ))}
            <th style={{ textAlign: 'right', padding: '7px 10px', fontSize: '0.6rem', color: 'var(--text-muted)', borderBottom: '1px solid var(--card-border)' }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isExp = expanded === i
            return (
              <tr key={i} onClick={() => extraKeys.length && toggleExpand(i)}
                style={{ borderBottom: '1px solid var(--card-border)', cursor: extraKeys.length ? 'pointer' : 'default', background: isExp ? 'var(--hover-bg)' : 'transparent' }}>
                {shown.map(k => (
                  <td key={k} style={{ padding: '8px 10px', color: 'var(--text-body)', verticalAlign: 'top' }}>
                    {Array.isArray(r[k]) || typeof r[k] === 'object'
                      ? <span style={{ fontFamily: 'monospace', fontSize: '0.66rem', color: 'var(--text-secondary)' }}>{formatValue(r[k], k)}</span>
                      : <span style={cellStyle(k, r[k])}>{formatValue(r[k], k)}</span>}
                  </td>
                ))}
                <td style={{ padding: '8px 10px', textAlign: 'right', color: color, fontSize: '0.62rem', whiteSpace: 'nowrap' }}>
                  {extraKeys.length ? (isExp ? '−' : '+') : ''}
                </td>
              </tr>
            )
          })}
          {expanded !== null && rows[expanded] && (
            <tr style={{ borderBottom: '1px solid var(--card-border)' }}>
              <td colSpan={shown.length + 1} style={{ padding: '10px 12px' }}>
                <div style={{ fontFamily: 'monospace', fontSize: '0.64rem', color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {extraKeys.map(k => (
                    <div key={k}>
                      <span style={{ color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.58rem' }}>{k.replace(/_/g, ' ')}: </span>
                      <span>{typeof rows[expanded][k] === 'object' ? JSON.stringify(rows[expanded][k], null, 1) : String(rows[expanded][k])}</span>
                    </div>
                  ))}
                </div>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}