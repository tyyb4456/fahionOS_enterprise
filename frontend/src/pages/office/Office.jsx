// frontend/src/pages/office/Office.jsx
// Virtual AI Office — a 3D environment page. Renders the office scene
// (room, desks, break room, supervisor office) with no agent characters or
// live activity feed — environment only.
import { Component, useEffect, useRef, useState } from 'react'
import { Building2, RotateCcw } from 'lucide-react'
import Office3D from './Office3D'

// Canvas can throw if WebGL is unavailable — keep the rest of the page usable.
class CanvasBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) {
      return (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, color: 'var(--text-muted)', textAlign: 'center', padding: 24 }}>
          <Building2 size={36} style={{ color: 'var(--gold)' }} />
          <div style={{ fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", letterSpacing: '0.06em' }}>3D office unavailable</div>
          <div style={{ fontSize: '0.8rem', maxWidth: 380, lineHeight: 1.5 }}>
            Your browser can&apos;t open a WebGL scene here.
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default function Office() {
  const [isMobile, setIsMobile] = useState(false)
  const sceneRef = useRef(null)

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 768)
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg)', minHeight: 0 }}>
      {/* Header */}
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        padding: '10px 16px', flexShrink: 0,
        background: 'var(--card-bg)', borderBottom: '1px solid var(--card-border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <Building2 size={18} style={{ color: 'var(--gold)', flexShrink: 0 }} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: "'Kola-Regular', serif", fontSize: '1rem', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
              Virtual AI Office
            </div>
            <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
              3D workspace · drag to look around
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <button onClick={() => sceneRef.current?.resetView()}
            title="Reset camera"
            style={iconBtn}>
            <RotateCcw size={14} />
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        {/* 3D canvas */}
        <div className="relative flex-1 min-w-0" style={{ minHeight: 0 }}>
          <CanvasBoundary>
            <Office3D
              ref={sceneRef}
              isMobile={isMobile}
            />
          </CanvasBoundary>
        </div>
      </div>
    </div>
  )
}

const iconBtn = {
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  width: 30, height: 30, borderRadius: 8, flexShrink: 0,
  background: 'var(--hover-bg)', border: '1px solid var(--card-border)',
  color: 'var(--text-secondary)', cursor: 'pointer', position: 'relative',
}