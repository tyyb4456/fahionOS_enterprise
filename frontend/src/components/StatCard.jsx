import { useState } from 'react'

const palette = {
  gold:   { bar: '#d4d4d8', text: '#d4d4d8', rgb: '212,212,216'  },
  teal:   { bar: '#d4d4d8', text: '#d4d4d8', rgb: '212,212,216'  },
  purple: { bar: '#a78bfa', text: '#a78bfa', rgb: '167,139,250' },
  red:    { bar: '#f87171', text: '#f87171', rgb: '239,68,68'   },
  yellow: { bar: '#facc15', text: '#facc15', rgb: '250,204,21'  },
  green:  { bar: '#4ade80', text: '#4ade80', rgb: '74,222,128'  },
  blue:   { bar: '#60a5fa', text: '#60a5fa', rgb: '96,165,250'  },
}

export default function StatCard({ label, value, sub, color = 'gold', icon: Icon }) {
  const c = palette[color] || palette.gold
  const [hov, setHov] = useState(false)

  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        position: 'relative',
        display: 'flex',
        alignItems: 'stretch',
        minHeight: 72,
        overflow: 'hidden',
        background: 'var(--item-bg)',
        border: `1px solid ${hov ? `rgba(${c.rgb},0.45)` : 'var(--item-border)'}`,
        boxShadow: hov ? '0 4px 18px rgba(0,0,0,0.2)' : 'none',
        transition: 'border-color 0.22s ease, box-shadow 0.22s ease',
        cursor: 'default',
      }}
    >
      {/* Left accent bar */}
      <div style={{
        width: 2,
        flexShrink: 0,
        background: c.bar,
        opacity: hov ? 0.9 : 0.45,
        transition: 'opacity 0.2s ease',
      }} />

      {/* Icon block */}
      {Icon && (
        <>
          <div style={{
            width: 54,
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <div style={{
              width: 32,
              height: 32,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: `rgba(${c.rgb},${hov ? 0.1 : 0.06})`,
              border: `1px solid rgba(${c.rgb},${hov ? 0.22 : 0.12})`,
              transition: 'background 0.2s ease, border-color 0.2s ease',
            }}>
              <Icon size={12} style={{
                color: c.text,
                opacity: hov ? 1 : 0.65,
                transition: 'opacity 0.2s ease',
              }} />
            </div>
          </div>

          <div style={{
            width: 1, flexShrink: 0, alignSelf: 'stretch',
            background: 'var(--item-border)', opacity: 0.5,
          }} />
        </>
      )}

      {/* Label + Value */}
      <div style={{
        flex: 1, padding: '12px 14px',
        display: 'flex', flexDirection: 'column',
        justifyContent: 'center', gap: 4, minWidth: 0,
      }}>
        <span style={{
          fontSize: '0.55rem', fontWeight: 600,
          textTransform: 'uppercase', letterSpacing: '0.12em',
          color: 'var(--text-secondary)', lineHeight: 1,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          fontFamily: "'Knewave', cursive",
        }}>
          {label}
        </span>

        <div style={{
          fontSize: '1.7rem', fontWeight: 300, lineHeight: 1,
          color: 'var(--text-primary)',
          fontFamily: "'Alfa Slab One', serif",
          fontVariantNumeric: 'tabular-nums',
        }}>
          {value ?? '—'}
        </div>

        {sub && (
          <div style={{
            fontSize: '0.6rem', fontWeight: 500,
            color: c.text, lineHeight: 1,
            fontFamily: "'Knewave', cursive",
          }}>
            {sub}
          </div>
        )}
      </div>
    </div>
  )
}
