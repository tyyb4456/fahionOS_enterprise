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
import { STAFF_HOME, SUP_HOME, AGENT_HOME } from './paths'
import { Room, BreakRoom } from './environment'
import { ConnectionLines, ActiveBeams, TravelingPacket, Pos } from './comms'
import { SupervisorStation, AgentStation } from './stations'
// import { MobileWorker } from './characters'

/* ══════════════════════════════════════════════════════════════════════════════
   MAIN SCENE — choreography orchestrator + Canvas wrapper (default export)
   ══════════════════════════════════════════════════════════════════════════════ */
function OfficeScene({ agents, supervisor, packets, selected, onSelect, isMobile, controlsRef }) {
  // ── Task-assignment choreography — the staff centre (break-room counter at
  //    the front) is every agent's home: they idle there until a task is
  //    assigned. A dispatch (idle→working) sends them up to the supervisor's
  //    office to receive the assignment, then on to their desk to work.
  //    Completion (→done) makes them walk back up to report, then return to
  //    the staff centre to idle.
  const [choreo, setChoreo] = useState({})
  const desiredRef = useRef({})   // key -> 'idle' | 'called' | 'report' | 'working'
  const busyRef = useRef({})      // a walk/hover is in progress
  const atDeskRef = useRef(Object.fromEntries(AGENT_ORDER.map(k => [k, false]))) // agents start at the staff centre
  const issuedRef = useRef({})    // last commanded choreo kind (dedupe)
  const prevStatusRef = useRef(null)
  const agentsRef = useRef(agents)
  useEffect(() => { agentsRef.current = agents }, [agents])

  // Resting yaw at the staff centre — agents face the counter (-z) with a
  // slight alternation so clustered neighbours read as chatting.
  const restFacing = useMemo(() => {
    const out = {}
    AGENT_ORDER.forEach((k, i) => { out[k] = i % 2 === 0 ? -0.18 : 0.18 })
    return out
  }, [])

  const issue = useCallback((key, kind, extra) => {
    if (busyRef.current[key]) return
    if (issuedRef.current[key] === kind) return
    issuedRef.current[key] = kind
    busyRef.current[key] = kind !== null
    if (kind && kind !== 'desk') atDeskRef.current[key] = false // leaving the desk (or en route)
    setChoreo(prev => {
      if (prev[key]?.kind === kind) return prev
      const next = { ...prev }
      if (kind) next[key] = { kind, ...extra }
      else delete next[key]
      return next
    })
  }, [])

  const decide = useCallback((key) => {
    if (busyRef.current[key]) return
    const desired = desiredRef.current[key]
    if (!desired) return
    if (desired === 'called') { if (!atDeskRef.current[key]) issue(key, 'called'); return }
    if (desired === 'report') { if (atDeskRef.current[key]) issue(key, 'report'); return }
    if (desired === 'working') { if (!atDeskRef.current[key]) issue(key, 'desk'); return }
    if (desired === 'idle') { if (atDeskRef.current[key]) issue(key, 'rest', { target: STAFF_HOME[key] }); return }
  }, [issue])

  // The worker sat down at its desk — it's now working (or done, waiting for
  // the next status flip to send it up to report).
  const handleSeated = useCallback((key) => {
    atDeskRef.current[key] = true
    busyRef.current[key] = false
    issuedRef.current[key] = null
    const st = (agentsRef.current[key] || {}).status || 'idle'
    desiredRef.current[key] = st === 'working' ? 'working' : 'idle'
    decide(key)
  }, [decide])

  // The worker reached the staff area (or any non-desk destination) — it idles
  // there until a new task is dispatched.
  const handleArrived = useCallback((key) => {
    atDeskRef.current[key] = false
    busyRef.current[key] = false
    issuedRef.current[key] = null
    const st = (agentsRef.current[key] || {}).status || 'idle'
    desiredRef.current[key] = st === 'working' ? 'called' : 'idle'
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
    // Run finished / reset — everyone clocks out to the staff area.
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
          staff centre (idle) · dispatched → supervisor (receive) → desk → work ·
          done → supervisor (report) → back to the staff centre. */}
      {/* <MobileWorker
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
      ))} */}

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
