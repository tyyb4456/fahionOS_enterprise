import { useState } from 'react'
import { Plus, Loader2, MessageSquare, Trash2, ChevronLeft, ChevronRight, PenSquare } from 'lucide-react'
import { GOLD } from './constants'
import { relativeTime } from './utils'

function ConvoItem({ convo, isActive, onSelect, onDelete }) {
  const [hovered, setHovered] = useState(false)

  return (
    <div
      onClick={() => onSelect(convo.thread_id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '8px 14px',
        background: isActive ? 'var(--hover-bg)' : hovered ? 'rgba(255,255,255,0.03)' : 'transparent',
        borderRadius: 8,
        margin: '1px 6px',
        cursor: 'pointer',
        display: 'flex', flexDirection: 'column', gap: 2,
        transition: 'all 0.12s',
        position: 'relative',
        borderLeft: `2px solid ${isActive ? GOLD : 'transparent'}`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
        <span style={{
          fontFamily: "'Knewave', cursive", fontSize: '0.78rem',
          color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
          lineHeight: 1.4, flex: 1,
          overflow: 'hidden', display: '-webkit-box',
          WebkitLineClamp: 1, WebkitBoxOrient: 'vertical',
          fontWeight: isActive ? 500 : 400,
        }}>
          {convo.title || 'Untitled'}
        </span>
        {hovered && (
          <button
            onClick={e => { e.stopPropagation(); onDelete(convo.thread_id) }}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-muted)', padding: '1px 2px', flexShrink: 0,
              transition: 'color 0.12s', borderRadius: 4,
            }}
            onMouseEnter={e => e.currentTarget.style.color = '#ef4444'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
            title="Delete"
          >
            <Trash2 size={11} />
          </button>
        )}
      </div>
      <span style={{
        fontFamily: "'Knewave', cursive", fontSize: '0.65rem',
        color: 'var(--text-muted)', opacity: 0.7,
      }}>
        {relativeTime(convo.updated_at)}
      </span>
    </div>
  )
}

export default function ConversationsSidebar({
  conversations, convosLoading, threadId,
  onSelect, onDelete, onNewThread,
  collapsed, onToggleCollapsed,
  isMobile,
}) {
  return (
    <>
      <div style={{
        width: collapsed ? 0 : 240,
        minWidth: collapsed ? 0 : 240,
        borderRight: collapsed ? 'none' : '1px solid var(--card-border)',
        display: 'flex', flexDirection: 'column',
        background: 'var(--sidebar-gradient)',
        transition: 'width 0.25s ease, min-width 0.25s ease',
        overflow: 'hidden',
        position: isMobile ? 'absolute' : 'relative',
        top: isMobile ? 0 : undefined,
        bottom: isMobile ? 0 : undefined,
        left: isMobile ? 0 : undefined,
        height: isMobile ? '100%' : undefined,
        zIndex: isMobile ? 5 : 2,
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 14px 12px',
          borderBottom: '1px solid var(--card-border)',
          flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{
            fontFamily: "'Knewave', cursive", fontSize: '0.65rem',
            letterSpacing: '0.12em', textTransform: 'uppercase',
            color: 'var(--text-muted)', fontWeight: 500,
          }}>
            Conversations
          </span>
          <button
            onClick={onNewThread}
            style={{
              width: 28, height: 28,
              background: 'none',
              border: '1px solid var(--card-border)',
              borderRadius: 8,
              color: 'var(--text-muted)',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.color = GOLD
              e.currentTarget.style.borderColor = 'rgba(212,212,216,0.35)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.color = 'var(--text-muted)'
              e.currentTarget.style.borderColor = 'var(--card-border)'
            }}
            title="New chat"
          >
            <PenSquare size={13} />
          </button>
        </div>

        {/* Conversations list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '6px 0' }}>
          {convosLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
              <Loader2 size={16} color="var(--text-muted)"
                style={{ animation: 'spin 1s linear infinite', opacity: 0.5 }} />
            </div>
          ) : conversations.length === 0 ? (
            <div style={{
              padding: '20px 14px',
              fontFamily: "'Knewave', cursive", fontSize: '0.72rem',
              color: 'var(--text-muted)', opacity: 0.6, textAlign: 'center', lineHeight: 1.6,
            }}>
              No chats yet.<br />Start a new conversation.
            </div>
          ) : (
            conversations.map(c => (
              <ConvoItem
                key={c.thread_id}
                convo={c}
                isActive={c.thread_id === threadId}
                onSelect={onSelect}
                onDelete={onDelete}
              />
            ))
          )}
        </div>
      </div>

      {/* Toggle button (Desktop only) */}
      {!isMobile && (
        <button
          onClick={onToggleCollapsed}
          style={{
            position: 'absolute',
            left: collapsed ? 0 : 240,
            top: '50%', transform: 'translateY(-50%)',
            zIndex: 10,
            background: 'var(--card-bg)',
            border: '1px solid var(--card-border)',
            borderLeft: collapsed ? '1px solid var(--card-border)' : 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer', padding: '6px 4px',
            transition: 'left 0.25s ease',
            borderRadius: collapsed ? '0 6px 6px 0' : '0 6px 6px 0',
          }}
          title={collapsed ? 'Show conversations' : 'Hide conversations'}
        >
          {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
        </button>
      )}
    </>
  )
}