import { Loader2, CheckCircle2, Workflow } from 'lucide-react'
import { sourceMeta } from './constants'

export default function AgentActivity({ steps = [], streaming = false, isMobile = false }) {
  if (!streaming || !steps || steps.length === 0) return null

  const seen = []
  for (const s of steps) {
    if (!seen.includes(s.source)) seen.push(s.source)
  }

  const last = steps[steps.length - 1]

  return (
    <div style={{
      margin: isMobile ? '0 16px' : '0 24px',
      background: 'var(--card-bg)',
      border: '1px solid var(--card-border)',
      borderRadius: 12,
      padding: isMobile ? '10px 12px' : '12px 16px',
      flexShrink: 0,
      animation: 'fadeUp 0.2s ease-out',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Workflow size={12} color="var(--text-muted)" style={{ opacity: 0.8 }} />
        <span style={{
          fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: '0.6rem', letterSpacing: '0.08em',
          textTransform: 'uppercase', color: 'var(--text-muted)', flex: 1,
        }}>
          Agent activity
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
        {seen.map(source => {
          const { label, color } = sourceMeta(source)
          const working = source === last.source
          return (
            <span key={source} style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: '0.58rem', letterSpacing: '0.05em',
              textTransform: 'uppercase', whiteSpace: 'nowrap',
              padding: '3px 9px', borderRadius: 999,
              color, border: `1px solid ${color}55`, background: `${color}14`,
            }}>
              {working
                ? <Loader2 size={9} color={color} style={{ animation: 'spin 0.9s linear infinite' }} />
                : <CheckCircle2 size={9} color="#22c55e" />}
              {label}
            </span>
          )
        })}
      </div>

      <div style={{
        fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: '0.58rem', color: 'var(--text-muted)', opacity: 0.75,
        letterSpacing: '0.02em',
      }}>
        {sourceMeta(last.source).label} · <span style={{ color: 'var(--text-secondary)' }}>{last.node || '…'}</span>
      </div>
    </div>
  )
}
