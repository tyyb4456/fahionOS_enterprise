import { Bot, Loader2 } from 'lucide-react'
import { GOLD } from './constants'
import ReasoningBlock from './ReasoningBlock'
import ToolCallCard from './ToolCallCard'
import MarkdownContent from './MarkdownContent'

export default function MessageBubble({ msg }) {
  const isUser = msg.role === 'user'

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: isUser ? 'flex-end' : 'flex-start',
      gap: 6,
      animation: 'fadeUp 0.22s ease-out',
    }}>
      {/* Role label */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        flexDirection: isUser ? 'row-reverse' : 'row',
        paddingLeft: isUser ? 0 : 2,
        paddingRight: isUser ? 2 : 0,
      }}>
        {!isUser && (
          <div style={{
            width: 20, height: 20,
            background: 'var(--card-bg)',
            border: '1px solid var(--card-border)',
            borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <Bot size={10} color="var(--text-muted)" />
          </div>
        )}
        <span style={{
          fontFamily: "'Knewave', cursive",
          fontSize: '0.65rem',
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: isUser ? 'var(--text-muted)' : 'var(--text-muted)',
          opacity: 0.8,
        }}>
          {isUser ? 'You' : 'FashionOS'}
        </span>
      </div>

      {/* Reasoning block */}
      {!isUser && msg.reasoning && (
        <ReasoningBlock text={msg.reasoning} streaming={msg.streaming && !msg.content} />
      )}

      {/* Tool calls */}
      {!isUser && msg.toolCalls && msg.toolCalls.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, width: '100%' }}>
          {msg.toolCalls.map(call => <ToolCallCard key={call.id} call={call} />)}
        </div>
      )}

      {/* Message bubble */}
      {(isUser || msg.content) && (
        <div style={{
          maxWidth: window.innerWidth <= 768 ? '90%' : '78%',
          background: isUser
            ? 'var(--card-bg)'
            : 'transparent',
          border: isUser ? '1px solid var(--card-border)' : 'none',
          borderRadius: isUser ? 18 : 0,
          padding: isUser ? '10px 16px' : '2px 0',
        }}>
          {msg.content ? (
            <MarkdownContent
              text={msg.content}
              color={isUser ? 'var(--text-primary)' : 'var(--text-body)'}
              fontSize="0.875rem"
            />
          ) : (
            <p style={{
              fontFamily: "'Knewave', cursive", fontSize: '0.875rem',
              lineHeight: 1.7, color: 'var(--text-body)', margin: 0,
            }}>
              {msg.streaming ? '' : '…'}
            </p>
          )}
          {msg.streaming && (
            <span style={{
              display: 'inline-block', width: 2, height: '0.85em',
              background: GOLD, marginLeft: 3, verticalAlign: 'text-bottom',
              animation: 'blink 0.9s step-end infinite',
            }} />
          )}
        </div>
      )}

      {/* Thinking indicator — 3 dot bounce */}
      {!isUser && msg.streaming && !msg.content && !msg.reasoning &&
        (!msg.toolCalls || msg.toolCalls.length === 0) && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '12px 0',
        }}>
          {[0, 0.2, 0.4].map((delay, i) => (
            <div key={i} style={{
              width: 5, height: 5, borderRadius: '50%',
              background: 'var(--text-muted)',
              opacity: 0.7,
              animation: 'bounce 1.4s infinite ease-in-out',
              animationDelay: `${delay}s`,
            }} />
          ))}
        </div>
      )}
    </div>
  )
}