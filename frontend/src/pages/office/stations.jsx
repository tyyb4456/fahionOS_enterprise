// frontend/src/pages/office/stations.jsx
// Agent/supervisor work stations: status rings, furniture, floating name
// tags with action bubbles and notification badges.
import { Html } from '@react-three/drei'
import { GOLD3, SUPERVISOR } from './config'
import { StatusLight, Desk, OfficeChair, GlassWalls, RoundDesk } from './furniture'

/* ══════════════════════════════════════════════════════════════════════════════
   FLOATING TAG — name + role + action bubble + notification badge
   ══════════════════════════════════════════════════════════════════════════════ */
export function Tag({ agent, status, selected, notify, action, onSelect }) {
  const { label, role, color } = agent
  const working = status === 'working'
  const bubbleText = status === 'done' ? 'Finished' : status === 'error' ? 'Failed' : (working ? (action || 'Working…') : (selected ? 'Viewing' : null))

  return (
    <group position={[0, 2.75, 0.4]}>
      <Html center distanceFactor={9} zIndexRange={[20, 0]} style={{ pointerEvents: 'none', userSelect: 'none' }}>
        <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
          {notify > 0 && (
            <div style={{
              position: 'absolute', top: -26, right: -14,
              minWidth: 16, height: 16, borderRadius: 8, padding: '0 4px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: '#ef4444', color: '#fff', fontSize: '0.6rem', fontWeight: 700,
              boxShadow: '0 0 8px rgba(239,68,68,0.7)',
            }}>
              {notify}
            </div>
          )}
          <div style={{
            fontFamily: "'Knewave', cursive", fontSize: '0.72rem', letterSpacing: '0.08em',
            textTransform: 'uppercase', whiteSpace: 'nowrap',
            color: working || selected ? color : '#9a9aa2',
            textShadow: '0 1px 4px rgba(0,0,0,0.9)',
            cursor: 'pointer',
          }}>
            {label}
          </div>
          {!working && (
            <div style={{
              fontSize: '0.58rem', whiteSpace: 'nowrap', opacity: 0.55,
              fontFamily: "'Knewave', cursive", letterSpacing: '0.04em', color: '#7c7c84',
            }}>
              {role}
            </div>
          )}
          {(working || bubbleText || selected) && (
            <div style={{
              marginTop: 1, padding: '3px 9px', borderRadius: 8, whiteSpace: 'nowrap',
              background: 'rgba(20,20,22,0.92)', border: `1px solid ${status === 'error' ? '#ef4444' : color}66`,
              color: status === 'error' ? '#ef4444' : color,
              fontSize: '0.62rem', fontFamily: "'Knewave', cursive", letterSpacing: '0.03em',
              maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis',
            }}>
              {bubbleText}
            </div>
          )}
          {working && (
            <div style={{ width: 26, height: 3, borderRadius: 2, overflow: 'hidden', background: 'rgba(255,255,255,0.08)' }}>
              <div style={{ width: '60%', height: '100%', borderRadius: 2, background: color, animation: 'office-slide 1.1s linear infinite' }} />
            </div>
          )}
        </div>
      </Html>
      <mesh
        position={[0, -2, 0.1]}
        onClick={e => { e.stopPropagation(); onSelect() }}
        onPointerOver={() => { document.body.style.cursor = 'pointer' }}
        onPointerOut={() => { document.body.style.cursor = 'auto' }}
      >
        <sphereGeometry args={[1.9, 8, 8]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   AGENT STATION — a full cubicle with a worker
   ══════════════════════════════════════════════════════════════════════════════ */
export function AgentStation({ agent, status, action, lastTool, selected, notify, onSelect }) {
  const { color } = agent
  return (
    <group position={[agent.pos.x, 0, agent.pos.z]} rotation-y={agent.rot}>
      <StatusLight color={color} status={status} selected={selected} radius={0.75} />
      <Desk color={color} status={status} selected={selected} />
      <OfficeChair />
      <Tag agent={agent} status={status} selected={selected} notify={notify} action={action} onSelect={() => onSelect(agent.key)} />
      {selected && lastTool && (
        <Html position={[0, 1.95, 0.1]} center distanceFactor={10} zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
          <div style={{ fontSize: '0.55rem', color: '#b9b9c1', fontFamily: "'Knewave', cursive", whiteSpace: 'nowrap', letterSpacing: '0.04em' }}>
            tool: {lastTool}
          </div>
        </Html>
      )}
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   SUPERVISOR — glass-walled corner office with a bigger desk + two monitors
   ══════════════════════════════════════════════════════════════════════════════ */
export function SupervisorStation({ status, action, notify, selected, onSelect }) {
  return (
    <group position={[SUPERVISOR.pos.x, 0, SUPERVISOR.pos.z]}>
      <StatusLight color={GOLD3} status={selected ? 'working' : 'idle'} selected={selected} />
      <GlassWalls />
      {/* Round executive desk — the CEO faces the team through the glass */}
      <RoundDesk color={GOLD3} status={status === 'idle' ? 'idle' : 'working'} selected={selected} />
      {/* CEO chair behind the round desk, facing the team */}
      <group position={[0, 0, -1.35]} rotation-y={Math.PI}>
        <OfficeChair />
      </group>
      <Tag agent={SUPERVISOR} status={selected ? 'working' : status} selected={selected} notify={notify} action={action} onSelect={() => onSelect('supervisor')} />
      {selected && (
        <Html position={[0, 1.95, 0.1]} center distanceFactor={10} zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
          <div style={{ fontSize: '0.55rem', color: '#d9d9df', fontFamily: "'Knewave', cursive", whiteSpace: 'nowrap', letterSpacing: '0.04em' }}>
            {action || 'Standing by'}
          </div>
        </Html>
      )}
    </group>
  )
}
