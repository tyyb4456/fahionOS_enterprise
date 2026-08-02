import { forwardRef } from 'react'
import { Send, Loader2, Plus } from 'lucide-react'
import { GOLD } from './constants'

const ChatComposer = forwardRef(function ChatComposer(
  { input, onChange, onKeyDown, onSend, isStreaming, centered },
  ref
) {
  return (
    <div style={{
      padding: centered ? '0' : '10px 24px 16px',
      borderTop: centered ? 'none' : '1px solid var(--card-border)',
      background: centered ? 'transparent' : 'var(--bg)',
      flexShrink: 0,
    }}>
      {/* Rounded pill input */}
      <div style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: 0,
        background: 'var(--card-bg)',
        border: '1px solid var(--card-border)',
        borderRadius: 24,
        padding: '10px 14px 10px 16px',
        transition: 'border-color 0.2s, box-shadow 0.2s',
        boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
      }}
        onFocusCapture={e => {
          e.currentTarget.style.borderColor = 'rgba(212,212,216,0.45)'
          e.currentTarget.style.boxShadow = '0 0 0 3px rgba(212,212,216,0.08)'
        }}
        onBlurCapture={e => {
          e.currentTarget.style.borderColor = 'var(--card-border)'
          e.currentTarget.style.boxShadow = '0 1px 4px rgba(0,0,0,0.15)'
        }}
      >
        {/* Plus icon (left) */}
        <button
          style={{
            width: 30, height: 30, flexShrink: 0,
            background: 'var(--hover-bg)',
            border: '1px solid var(--card-border)',
            borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', marginRight: 10, alignSelf: 'flex-end',
            color: 'var(--text-muted)', transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.color = 'var(--text-secondary)'
            e.currentTarget.style.borderColor = 'rgba(255,255,255,0.18)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.color = 'var(--text-muted)'
            e.currentTarget.style.borderColor = 'var(--card-border)'
          }}
          title="Add attachment"
        >
          <Plus size={13} />
        </button>

        {/* Textarea */}
        <textarea
          ref={ref}
          rows={1}
          value={input}
          onChange={onChange}
          onKeyDown={onKeyDown}
          placeholder="How can I help you today?"
          disabled={isStreaming}
          style={{
            flex: 1, background: 'transparent', border: 'none', outline: 'none',
            resize: 'none',
            fontFamily: "'Knewave', cursive",
            fontSize: '0.875rem',
            color: 'var(--text-primary)',
            lineHeight: 1.6,
            minHeight: 24, maxHeight: 140,
            overflowY: 'auto',
            padding: '2px 0',
            opacity: isStreaming ? 0.5 : 1,
          }}
          onInput={e => {
            e.target.style.height = 'auto'
            e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'
          }}
        />

        {/* Right side: model label + send */}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, marginLeft: 10, flexShrink: 0, alignSelf: 'flex-end' }}>
          <span style={{
            fontFamily: "'Knewave', cursive",
            fontSize: '0.65rem',
            color: 'var(--text-muted)',
            letterSpacing: '0.04em',
            whiteSpace: 'nowrap',
            paddingBottom: 4,
            opacity: 0.7,
          }}>
            FashionOS
          </span>

          {/* Send button */}
          <button
            onClick={onSend}
            disabled={!input.trim() || isStreaming}
            style={{
              width: 32, height: 32, flexShrink: 0,
              background: (!input.trim() || isStreaming) ? 'var(--hover-bg)' : GOLD,
              border: 'none',
              borderRadius: '50%',
              cursor: (!input.trim() || isStreaming) ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.18s',
            }}
            onMouseEnter={e => {
              if (input.trim() && !isStreaming) {
                e.currentTarget.style.transform = 'scale(1.05)'
                e.currentTarget.style.background = '#ffffff'
              }
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = 'scale(1)'
              e.currentTarget.style.background = (!input.trim() || isStreaming) ? 'var(--hover-bg)' : GOLD
            }}
          >
            {isStreaming
              ? <Loader2 size={13} color={GOLD} style={{ animation: 'spin 1s linear infinite' }} />
              : <Send    size={13} color={!input.trim() ? 'var(--text-muted)' : '#fff'} />}
          </button>
        </div>
      </div>

      {/* Hint */}
      {!centered && (
        <p style={{
          fontFamily: "'Knewave', cursive",
          fontSize: '0.6rem',
          color: 'var(--text-muted)',
          opacity: 0.6,
          letterSpacing: '0.04em',
          marginTop: 6, marginBottom: 0, textAlign: 'center',
        }}>
          Enter to send · Shift+Enter for new line
        </p>
      )}
    </div>
  )
})

export default ChatComposer