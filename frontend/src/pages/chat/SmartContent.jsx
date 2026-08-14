import { useState } from 'react'
import { ChevronUp, ChevronDown, Database, AlertTriangle } from 'lucide-react'
import PrettyJSON from './PrettyJSON'
import MarkdownContent from './MarkdownContent'

// Split a streamed blob into text segments and JSON segments (concatenated
// JSON arrays/objects often arrive glued together with no separator).
function parseSmartContent(text) {
  if (!text) return []
  const segments = []
  let i = 0
  while (i < text.length) {
    const ch = text[i]
    if (ch === '{' || ch === '[') {
      let depth = 0, inStr = false, esc = false, j = i
      for (; j < text.length; j++) {
        const c = text[j]
        if (inStr) {
          if (esc) esc = false
          else if (c === '\\') esc = true
          else if (c === '"') inStr = false
        } else {
          if (c === '"') inStr = true
          else if (c === '{' || c === '[') depth++
          else if (c === '}' || c === ']') {
            depth--
            if (depth === 0) { j++; break }
          }
        }
      }
      const candidate = text.slice(i, j)
      try {
        const parsed = JSON.parse(candidate)
        const prev = segments[segments.length - 1]
        // Drop consecutive duplicates (e.g. the same error echoed twice).
        if (!(prev && prev.type === 'json' && JSON.stringify(prev.value) === JSON.stringify(parsed))) {
          segments.push({ type: 'json', value: parsed })
        }
        i = j
        continue
      } catch {
        // Not valid JSON — fall through and treat as text.
      }
    }
    let k = i
    while (k < text.length && text[k] !== '{' && text[k] !== '[') k++
    const t = text.slice(i, k).trim()
    if (t) segments.push({ type: 'text', text: t })
    i = k
  }
  return segments
}

function describe(value) {
  if (Array.isArray(value)) {
    if (value.length === 0) return { label: 'Empty list' }
    if (value.every(v => v && typeof v === 'object' && 'error' in v)) {
      return { label: `${value.length} error${value.length > 1 ? 's' : ''}`, error: true }
    }
    const s = value.find(v => v && typeof v === 'object' && typeof v.summary === 'string')
    return { label: `${value.length} item${value.length === 1 ? '' : 's'}`, subtitle: s && s.summary }
  }
  if (value && typeof value === 'object') {
    if (typeof value.summary === 'string') return { label: 'Decision', subtitle: value.summary }
    if (typeof value.error === 'string') return { label: 'Error', subtitle: value.error, error: true }
    const keys = Object.keys(value)
    return { label: keys.length ? keys.map(k => k.replace(/_/g, ' ')).join(' · ') : 'Object' }
  }
  return { label: typeof value }
}

function JsonBlock({ value }) {
  const [open, setOpen] = useState(
    !!(value && typeof value === 'object' && !Array.isArray(value) && typeof value.summary === 'string')
  )
  const { label, subtitle, error } = describe(value)
  const isPrimitiveList = Array.isArray(value) && value.every(v => !v || typeof v !== 'object')

  return (
    <div style={{
      border: `1px solid ${error ? '#ef444455' : 'var(--item-border)'}`,
      background: error ? '#ef44440a' : 'var(--inner-bg)',
      borderRadius: 8, overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 7,
          background: 'none', border: 'none', cursor: 'pointer', padding: '6px 10px',
          textAlign: 'left',
        }}
      >
        {error
          ? <AlertTriangle size={11} color="#ef4444" style={{ flexShrink: 0 }} />
          : <Database size={11} color="var(--text-muted)" style={{ flexShrink: 0 }} />}
        <span style={{
          fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: '0.58rem', letterSpacing: '0.07em',
          textTransform: 'uppercase', color: error ? '#ef4444' : 'var(--text-secondary)',
          flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {label}
        </span>
        {open
          ? <ChevronUp size={11} color="var(--text-muted)" style={{ flexShrink: 0 }} />
          : <ChevronDown size={11} color="var(--text-muted)" style={{ flexShrink: 0 }} />}
      </button>

      {subtitle && !open && (
        <div style={{
          padding: '0 10px 8px', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: '0.62rem',
          color: 'var(--text-muted)', opacity: 0.85, lineHeight: 1.5,
        }}>
          {subtitle}
        </div>
      )}

      {open && (
        <div style={{ padding: '4px 10px 10px', borderTop: '1px dashed var(--item-border)' }}>
          {isPrimitiveList ? (
            <ul style={{ margin: 0, paddingLeft: '1.1em', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {value.map((v, i) => (
                <li key={i} style={{
                  fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: '0.62rem',
                  color: 'var(--text-secondary)', lineHeight: 1.5,
                }}>{String(v)}</li>
              ))}
            </ul>
          ) : (
            <PrettyJSON value={value} />
          )}
        </div>
      )}
    </div>
  )
}

export default function SmartContent({ text }) {
  const segments = parseSmartContent(text)
  if (segments.length === 0) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {segments.map((seg, i) =>
        seg.type === 'json'
          ? <JsonBlock key={i} value={seg.value} />
          : <MarkdownContent key={i} text={seg.text} color="var(--text-secondary)" fontSize="0.7rem" />
      )}
    </div>
  )
}
