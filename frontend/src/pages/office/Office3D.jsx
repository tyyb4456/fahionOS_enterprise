// frontend/src/pages/office/Office3D.jsx
// Virtual AI Office - 3D scene entry. OfficeScene is the choreography/
// orchestrator that assembles focused modules from this folder:
//   paths.js         - walkway routing, break-room seats, home/visit spots
//   materials.js     - shared color + material palettes
//   furniture.jsx    - desks, chairs, monitors, lamps, supervisor office
//   environment.jsx  - room, carpet, skyline windows, break room, rails
//   characters.jsx   - worker figures + choreographed MobileWorker
//   stations.jsx     - name tags + agent/supervisor stations
//   comms.jsx        - travelling packets, connection lines, active beams
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { agentMeta, AGENT_ORDER, SUPERVISOR, GOLD3 } from './config'
import { BAR_SEATS, agentSeat, faceDir, SUP_HOME, AGENT_HOME } from './paths'
import { Room, BreakRoom } from './environment'
import { ConnectionLines, ActiveBeams, TravelingPacket, Pos } from './comms'
import { SupervisorStation, AgentStation } from './stations'
import { MobileWorker } from './characters'

/* ══════════════════════════════════════════════════════════════════════════════
   MAIN SCENE — choreography orchestrator + Canvas wrapper (default export)
   ══════════════════════════════════════════════════════════════════════════════ */
function OfficeScene({ agents, supervisor, packets, selected, onSelect, isMobile, controlsRef }) {
  // ── Task-assignment choreography — driven purely by feed status transitions:
  //    idle agents hang out at the break room; a dispatch (idle→working) makes
  //    the agent walk up to the supervisor's office to receive the task, return
  //    to its desk and work; completion (→done) makes it walk up to report, then
  //    head back to the break room (or stay put if it goes straight back to work).
  const [choreo, setChoreo] = useState({})
  const desiredRef = useRef({})   // key -> 'idle' | 'called' | 'report' | 'working'
  const busyRef = useRef({})      // a walk/hover is in progress
  const atDeskRef = useRef(Object.fromEntries(AGENT_ORDER.map(k => [k, true])))
  const issuedRef = useRef({})    // last commanded choreo kind (dedupe)
  const prevStatusRef = useRef(null)
  const agentsRef = useRef(agents)
  useEffect(() => { agentsRef.current = agents }, [agents])

  // ── Break-room seat assignment — idle agents claim the nearest free seat so
  //    they spread around the counter instead of lining up at one point. ──
  const [seatMap, setSeatMap] = useState({})        // key -> BAR_SEATS index
  const seatMapRef = useRef({})
  const assignSeat = useCallback((key) => {
    if (seatMapRef.current[key] != null) return seatMapRef.current[key]
    const taken = new Set(Object.values(seatMapRef.current))
    const from = agentSeat(key) // proxy for the agent's position when it goes idle
    let best = 0
    let bestD = Infinity
    BAR_SEATS.forEach((s, i) => {
      if (taken.has(i)) return
      const d = from.distanceTo(s)
      if (d < bestD) { bestD = d; best = i }
    })
    const next = { ...seatMapRef.current, [key]: best }
    seatMapRef.current = next
    setSeatMap(next)
    return best
  }, [])
  const releaseSeat = useCallback((key) => {
    if (seatMapRef.current[key] == null) return
    const next = { ...seatMapRef.current }
    delete next[key]
    seatMapRef.current = next
    setSeatMap(next)
  }, [])
  // Facing for each resting agent: face the counter (yaw 0), but turn slightly
  // toward an idle neighbour in an adjacent seat so pairs read as chatting.
  const restFacing = useMemo(() => {
    const out = {}
    const keys = AGENT_ORDER.filter(k => seatMap[k] != null)
    for (const k of keys) {
      const pos = BAR_SEATS[seatMap[k]]
      let yaw = 0
      let best = null
      let bestD = Infinity
      for (const m of keys) {
        if (m === k) continue
        const other = BAR_SEATS[seatMap[m]]
        const d = Math.hypot(other.x - pos.x, other.z - pos.z)
        if (d < bestD) { bestD = d; best = other }
      }
      if (best && bestD <= 3.0) yaw = faceDir(pos, best) * 0.45
      out[k] = yaw
    }
    return out
  }, [seatMap])

  const issue = useCallback((key, kind, extra) => {
    if (busyRef.current[key]) return
    if (issuedRef.current[key] === kind) return
    issuedRef.current[key] = kind
    busyRef.current[key] = kind !== null
    if (kind && kind !== 'desk') atDeskRef.current[key] = false
    if (kind && kind !== 'rest') releaseSeat(key) // leaving idle frees the seat
    setChoreo(prev => {
      if (prev[key]?.kind === kind) return prev
      const next = { ...prev }
      if (kind) next[key] = { kind, ...extra }
      else delete next[key]
      return next
    })
  }, [releaseSeat])

  const decide = useCallback((key) => {
    if (busyRef.current[key]) return
    const desired = desiredRef.current[key]
    if (!desired) return
    if (desired === 'called') { issue(key, 'called'); return }
    if (desired === 'report') { issue(key, 'report'); return }
    if (desired === 'working') { if (!atDeskRef.current[key]) issue(key, 'desk'); return }
    if (desired === 'idle') {
      if (atDeskRef.current[key]) {
        const idx = assignSeat(key)
        issue(key, 'rest', { target: BAR_SEATS[idx] })
      }
      return
    }
  }, [assignSeat, issue])

  // The worker sat back down at its desk — decide what it should do next from
  // the agent's current feed status.
  const handleSeated = useCallback((key) => {
    atDeskRef.current[key] = true
    busyRef.current[key] = false
    issuedRef.current[key] = null
    const st = (agentsRef.current[key] || {}).status || 'idle'
    desiredRef.current[key] = st === 'working' ? 'working' : 'idle'
    decide(key)
  }, [decide])

  const handleArrived = useCallback((key) => {
    busyRef.current[key] = false
    issuedRef.current[key] = null
    decide(key)
  }, [decide])

  // Feed → desired-state mapping (fires on real status transitions only).
  useEffect(() => {
    const statuses = {}
    AGENT_ORDER.forEach(key => { statuses[key] = (agents[key] || {}).status || 'idle' })
    const supStatus = supervisor.status || 'idle'
    const prev = prevStatusRef.current

    // First pass — seed from whatever the feed already reports (snapshot).
    if (!prev) {
      AGENT_ORDER.forEach(key => {
        const st = statuses[key]
        desiredRef.current[key] = st === 'working' ? 'called' : st === 'done' ? 'report' : 'idle'
      })
      prevStatusRef.current = { supervisor: supStatus, agents: statuses }
      AGENT_ORDER.forEach(key => decide(key))
      return
    }

    AGENT_ORDER.forEach(key => {
      const cur = statuses[key]
      const before = prev.agents[key] || 'idle'
      if (cur !== before) {
        if (cur === 'working') desiredRef.current[key] = 'called'
        else if (cur === 'done') desiredRef.current[key] = 'report'
        else desiredRef.current[key] = 'idle' // idle / error
        decide(key)
      }
    })
    // Run finished / reset — everyone clocks out to the break room.
    if (supStatus === 'idle' && prev.supervisor !== 'idle') {
      AGENT_ORDER.forEach(key => { desiredRef.current[key] = 'idle'; decide(key) })
    }
    prevStatusRef.current = { supervisor: supStatus, agents: statuses }
  }, [agents, supervisor, decide])

  return (
    <>
      <color attach="background" args={['#0b0b0e']} />
      <fog attach="fog" args={['#0b0b0e', 30, 52]} />

      <Room />
      <BreakRoom />

      {/* Lighting — even natural light only (no localized pools on walls/floor) */}
      <ambientLight intensity={0.55} color="#c9ccd4" />
      <hemisphereLight args={['#b4bccd', '#14141a', 0.75]} />
      <directionalLight
        position={[7, 12, 9]}
        intensity={2.4}
        color="#ffe9c8"
        castShadow={!isMobile}
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-camera-left={-20}
        shadow-camera-right={20}
        shadow-camera-top={20}
        shadow-camera-bottom={-20}
        shadow-camera-near={1}
        shadow-camera-far={48}
      />
      <directionalLight position={[-8, 7, -5]} intensity={0.55} color="#cfe0ff" />
      <directionalLight position={[0, 8, -13]} intensity={0.55} color="#8fa2c2" />

      {/* Furniture */}
      <ConnectionLines />
      <ActiveBeams agents={agents} />
      <SupervisorStation
        status={supervisor.status}
        action={supervisor.action}
        selected={selected === 'supervisor'}
        notify={supervisor.unread || 0}
        onSelect={onSelect}
      />
      {AGENT_ORDER.map(key => {
        const a = agentMeta(key)
        const s = agents[key] || { status: 'idle', action: '' }
        return (
          <AgentStation
            key={key}
            agent={a}
            status={s.status}
            action={s.action}
            lastTool={s.lastTool}
            selected={selected === key}
            notify={s.unread || 0}
            onSelect={onSelect}
          />
        )
      })}

      {/* Moving workers — choreographed by the task-assignment state machine:
          idle → break room · dispatched → supervisor (receive) → desk → work ·
          done → supervisor (report) → break room again. */}
      <MobileWorker
        key="supervisor-mover"
        choreo={null}
        restFacing={0}
        color={GOLD3}
        status={supervisor.status}
        variant={0}
        seatedFacing={Math.PI}
        home={SUP_HOME}
        keyName="supervisor"
        onSeated={handleSeated}
        onArrived={handleArrived}
      />
      {AGENT_ORDER.map(key => (
        <MobileWorker
          key={`agent-${key}`}
          choreo={choreo[key] || null}
          restFacing={restFacing[key] || 0}
          status={(agents[key] || {}).status || 'idle'}
          variant={AGENT_ORDER.indexOf(key)}
          seatedFacing={agentMeta(key).rot}
          home={AGENT_HOME[key]}
          keyName={key}
          onSeated={handleSeated}
          onArrived={handleArrived}
        />
      ))}

      {/* Communication packets */}
      {packets.map(p => {
        const from = p.from === 'supervisor' ? Pos(SUPERVISOR.pos) : Pos(agentMeta(p.from).pos)
        const to = p.to === 'supervisor' ? Pos(SUPERVISOR.pos) : Pos(agentMeta(p.to).pos)
        const color = p.from === 'supervisor' ? GOLD3 : (agentMeta(p.from).color || GOLD3)
        return <TravelingPacket key={p.id} from={from} to={to} color={color} />
      })}

      {/* Shadow catcher */}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.004, 0]} receiveShadow>
        <planeGeometry args={[44, 44]} />
        <shadowMaterial transparent opacity={0.4} />
      </mesh>

      <OrbitControls
        ref={controlsRef}
        target={[0, 1.4, -2.5]}
        minDistance={6}
        maxDistance={34}
        maxPolarAngle={Math.PI / 2.15}
        enablePan={false}
        makeDefault
      />
    </>
  )
}
/* ══════════════════════════════════════════════════════════════════════════════
   CANVAS WRAPPER
   ══════════════════════════════════════════════════════════════════════════════ */
const Office3D = forwardRef(function Office3D({ agents, supervisor, packets, selected, onSelect, isMobile }, ref) {
  const controlsRef = useRef(null)

  useImperativeHandle(ref, () => ({
    resetView: () => controlsRef.current?.reset?.(),
  }))

  return (
    <Canvas
      shadows={!isMobile}
      dpr={[1, 1.8]}
      camera={{ position: [0, 6.4, 18], fov: 45 }}
      style={{ touchAction: 'none' }}
    >
      <OfficeScene
        agents={agents}
        supervisor={supervisor}
        packets={packets}
        selected={selected}
        onSelect={onSelect}
        isMobile={isMobile}
        controlsRef={controlsRef}
      />
    </Canvas>
  )
})

export default Office3D
