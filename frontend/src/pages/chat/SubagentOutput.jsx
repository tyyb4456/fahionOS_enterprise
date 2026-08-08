import { useState } from 'react'
import { Loader2, CheckCircle2, ChevronUp, ChevronDown } from 'lucide-react'
import { sourceMeta } from './constants'
import MarkdownContent from './MarkdownContent'
import SmartContent from './SmartContent'

function Reasoning({ text, color }) {
  const [open, setOpen] = useState(false)
  if (!text) return null
  return (
    <div style={{
      borderLeft: `2px solid ${color}66`, padding: '4px 0 4px 10px', margin: '0 0 8px',
      background: `${color}0a`,
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'none', border: 'none', cursor: 'pointer', padding: 0,
          fontFamily: "'Knewave', cursive", fontSize: '0.55rem', letterSpacing: '0.08em',
          textTransform: 'uppercase', color: 'var(--text-muted)',
        }}
      >
        {open ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
        thinking
      </button>
      {open && (
        <div style={{ marginTop: 4 }}>
          <MarkdownContent text={text} color="var(--text-muted)" fontSize="0.66rem" italic />
        </div>
      )}
    </div>
  )
}

export default function SubagentOutput({ streams = {}, activeSource = null, streaming = false }) {
  const [manual, setManual] = useState({})
  const sources = Object.keys(streams)
  if (sources.length === 0) return null

  const isExpanded = source => {
    if (source in manual) return manual[source]
    return streaming && source === activeSource
  }

  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 6 }}>
      {sources.map(source => {
        const { label, color } = sourceMeta(source)
        const stream = streams[source] || {}
        const hasBody = (stream.reasoning || '').length > 0 || (stream.content || '').length > 0
        const active = streaming && source === activeSource
        const expanded = isExpanded(source)
        const hasContent = (stream.content || '').length > 0
        const hasReasoning = (stream.reasoning || '').length > 0

        return (
          <div key={source} style={{
            background: 'var(--item-bg)', border: `1px solid ${active ? color + '66' : 'var(--item-border)'}`,
            borderRadius: 10, overflow: 'hidden',
            transition: 'border-color 0.25s ease',
            boxShadow: active ? `0 0 0 3px ${color}14` : 'none',
          }}>
            <button
              onClick={() => setManual(m => ({ ...m, [source]: !isExpanded(source) }))}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                background: 'none', border: 'none', cursor: 'pointer', padding: '7px 11px',
                textAlign: 'left',
              }}
            >
              <span style={{
                width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                background: active ? color : `${color}88`,
                boxShadow: active ? `0 0 6px ${color}` : 'none',
              }} />
              <span style={{
                fontFamily: "'Knewave', cursive", fontSize: '0.62rem', letterSpacing: '0.06em',
                textTransform: 'uppercase', color: 'var(--text-secondary)', flex: 1, whiteSpace: 'nowrap',
                overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {label}
                {hasBody && !active && !streaming && (
                  <span style={{ color: 'var(--text-muted)', opacity: 0.7, letterSpacing: '0.02em' }}>
                    {' '}· {(stream.content || '').length > 0 ? 'output' : 'thinking'}
                  </span>
                )}
              </span>
              {active
                ? <Loader2 size={11} color={color} style={{ animation: 'spin 0.9s linear infinite', flexShrink: 0 }} />
                : hasBody
                  ? <CheckCircle2 size={11} color="#22c55e" style={{ flexShrink: 0 }} />
                  : <span style={{ width: 11, flexShrink: 0 }} />}
              {(hasBody && !active) && (expanded ? <ChevronUp size={11} color="var(--text-muted)" style={{ flexShrink: 0 }} /> : <ChevronDown size={11} color="var(--text-muted)" style={{ flexShrink: 0 }} />)}
            </button>

            {expanded && hasBody && (
              <div style={{ padding: '2px 12px 10px', borderTop: '1px dashed var(--item-border)' }}>
                {hasReasoning && <Reasoning text={stream.reasoning} color={color} />}
                {hasContent && <SmartContent text={stream.content} />}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
