import { Loader2 } from 'lucide-react'

export function Spinner({ size = 18, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)' }}>
      <Loader2 size={size} style={{ animation: 'spin 1s linear infinite', opacity: 0.6 }} />
      {label && <span style={{ fontSize: '0.72rem', letterSpacing: '0.04em' }}>{label}</span>}
    </div>
  )
}

export function Card({ children, style }) {
  return (
    <div className="page-card space-y-4" style={{ padding: '20px', ...style }}>
      {children}
    </div>
  )
}

export function Field({ label, name, value, onChange, placeholder, type = 'text', hint }) {
  const inputBase = {
    width: '100%', background: 'var(--input-bg)',
    border: '1px solid var(--input-border)', borderRadius: '10px',
    padding: '9px 12px', fontSize: '0.875rem', color: 'var(--text-body)', outline: 'none',
  }
  return (
    <div>
      <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{label}</label>
      <input name={name} type={type} value={value || ''} onChange={onChange} placeholder={placeholder} style={inputBase}
        onFocus={e => e.target.style.borderColor = 'var(--gold)'}
        onBlur={e => e.target.style.borderColor = 'var(--input-border)'} />
      {hint && <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{hint}</p>}
    </div>
  )
}

export function Pill({ children, color = 'var(--gold)', bg, border }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '2px 10px', borderRadius: 999,
      background: bg || 'var(--item-bg)', border: border || `1px solid ${color}44`,
      color, fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif",
      fontSize: '0.6rem', letterSpacing: '0.06em', textTransform: 'uppercase', whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  )
}

export function PageHeader({ eyebrow, title, sub, right }) {
  return (
    <div>
      <div className="section-pill">{eyebrow}</div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <h1 className="page-title-shimmer text-2xl" style={{ fontFamily: "'Kola-Regular', serif", lineHeight: 1.15 }}>
          {title}
        </h1>
        {right}
      </div>
      {sub && <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{sub}</p>}
      <div className="gradient-accent-line" />
    </div>
  )
}

export function EmptyState({ text }) {
  return (
    <div style={{
      padding: '28px 16px', color: 'var(--text-muted)', fontSize: '0.75rem',
      textAlign: 'center', lineHeight: 1.6, border: '1px dashed var(--card-border)', borderRadius: '10px',
    }}>
      {text}
    </div>
  )
}

export function SuccessToast({ text }) {
  return (
    <div className="rounded-xl px-4 py-3 text-sm"
      style={{ background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.2)', color: '#4ade80' }}>
      {text}
    </div>
  )
}