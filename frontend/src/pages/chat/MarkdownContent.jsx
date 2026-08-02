import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { GOLD } from './constants'

export default function MarkdownContent({ text, color = 'var(--text-body)', fontSize = '0.82rem', italic = false }) {
  const base = { fontFamily: "'Knewave', cursive", color, lineHeight: 1.7, fontSize }

  return (
    <div style={{ ...base, fontStyle: italic ? 'italic' : 'normal' }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p:  ({ children }) => <p style={{ margin: '0 0 10px', wordBreak: 'break-word' }}>{children}</p>,
          h1: ({ children }) => <h1 style={{ ...base, fontSize: '1.05em', fontWeight: 600, color: 'var(--text-primary)', margin: '14px 0 8px', letterSpacing: '0.01em' }}>{children}</h1>,
          h2: ({ children }) => <h2 style={{ ...base, fontSize: '1em', fontWeight: 600, color: 'var(--text-primary)', margin: '14px 0 8px', letterSpacing: '0.01em' }}>{children}</h2>,
          h3: ({ children }) => <h3 style={{ ...base, fontSize: '0.95em', fontWeight: 600, color: GOLD, margin: '12px 0 6px', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.72rem' }}>{children}</h3>,
          strong: ({ children }) => <strong style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{children}</strong>,
          em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,
          ul: ({ children }) => <ul style={{ margin: '0 0 10px', paddingLeft: '1.2em' }}>{children}</ul>,
          ol: ({ children }) => <ol style={{ margin: '0 0 10px', paddingLeft: '1.2em' }}>{children}</ol>,
          li: ({ children }) => <li style={{ margin: '3px 0' }}>{children}</li>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: GOLD, textDecoration: 'underline', textUnderlineOffset: 2 }}>
              {children}
            </a>
          ),
          code: ({ inline, children }) =>
            inline ? (
              <code style={{
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                background: 'var(--subtle-bg)', border: '1px solid var(--subtle-border)',
                padding: '1px 5px', fontSize: '0.9em', color: GOLD,
              }}>{children}</code>
            ) : (
              <code style={{ fontFamily: "'JetBrains Mono', 'Fira Code', monospace", fontSize: '0.85em' }}>{children}</code>
            ),
          pre: ({ children }) => (
            <pre style={{
              background: 'var(--bg)', border: '1px solid var(--card-border)',
              padding: '10px 12px', overflowX: 'auto', margin: '0 0 10px',
            }}>{children}</pre>
          ),
          blockquote: ({ children }) => (
            <blockquote style={{
              borderLeft: `2px solid ${GOLD}55`, margin: '0 0 10px', padding: '2px 0 2px 12px',
              color: 'var(--text-secondary)',
            }}>{children}</blockquote>
          ),
          hr: () => <hr style={{ border: 'none', borderTop: '1px solid var(--card-border)', margin: '12px 0' }} />,
          table: ({ children }) => (
            <div style={{ overflowX: 'auto', marginBottom: 10 }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: '0.9em' }}>{children}</table>
            </div>
          ),
          th: ({ children }) => <th style={{ textAlign: 'left', padding: '5px 8px', borderBottom: '1px solid var(--subtle-border)', color: 'var(--text-primary)', fontWeight: 600 }}>{children}</th>,
          td: ({ children }) => <td style={{ padding: '5px 8px', borderBottom: '1px solid var(--card-border)' }}>{children}</td>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}