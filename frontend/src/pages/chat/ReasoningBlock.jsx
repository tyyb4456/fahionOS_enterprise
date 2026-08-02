import { useState } from 'react'
import { Loader2, ChevronUp, ChevronDown, Sparkles } from 'lucide-react'
import MarkdownContent from './MarkdownContent'

export default function ReasoningBlock({ text, streaming }) {
  const [expanded, setExpanded] = useState(false)
  const [hovered, setHovered] = useState(false)

  if (!text) return null

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: '100%',
        background: 'var(--inner-bg)',
        borderLeft: '2px solid var(--gold)',
        borderTop: '1px solid var(--item-border)',
        borderRight: '1px solid var(--item-border)',
        borderBottom: '1px solid var(--item-border)',
        borderRadius: '0 8px 8px 0',
        transition: 'all 0.22s ease',
        boxShadow: hovered ? '0 4px 12px rgba(0,0,0,0.03)' : 'none',
        marginBottom: 12,
      }}
    >
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '10px 14px',
          cursor: 'pointer',
          userSelect: 'none',
        }}
      >
        {streaming ? (
          <Loader2
            size={12}
            style={{
              color: 'var(--gold)',
              animation: 'spin 1.2s linear infinite',
              flexShrink: 0,
            }}
          />
        ) : (
          <Sparkles
            size={12}
            style={{
              color: 'var(--text-muted)',
              flexShrink: 0,
            }}
          />
        )}
        <span
          style={{
            fontFamily: "'Knewave', cursive",
            fontSize: '0.62rem',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--text-secondary)',
            flex: 1,
          }}
        >
          {streaming ? 'thinking…' : 'thinking'}
        </span>
        {expanded ? (
          <ChevronUp size={12} style={{ color: 'var(--text-muted)', opacity: hovered ? 1 : 0.6, transition: 'opacity 0.2s' }} />
        ) : (
          <ChevronDown size={12} style={{ color: 'var(--text-muted)', opacity: hovered ? 1 : 0.6, transition: 'opacity 0.2s' }} />
        )}
      </div>
      {expanded && (
        <div
          style={{
            padding: '4px 14px 14px',
            borderTop: '1px dashed var(--item-border)',
            background: 'rgba(var(--gold-rgb), 0.01)',
          }}
        >
          <MarkdownContent
            text={text}
            color="var(--text-secondary)"
            fontSize="0.68rem"
            italic
          />
        </div>
      )}
    </div>
  )
}
