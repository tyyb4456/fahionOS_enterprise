// frontend/src/pages/office/characters.jsx
// Worker figures (seated + standing) and the choreographed MobileWorker
// avatar that walks paths between the desk, supervisor office and break room.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'
import { SUPERVISOR } from './config'
import { toColor, SKINS, HAIRS } from './materials'
import {
  WALK_SPEED, HOVER_MS, REPORT_LEG_MS, faceDir, v3,
  pathToSupervisor, pathToDesk, pathToRest, STAFF_HOME,
} from './paths'
import { GLTFAvatar } from './GLTFAvatar'

const TEST_GLTF_AGENT = 'marketing_agent' // swap to whichever agent you want to test

export function WorkerHead({ skin, hair, hairStyle, y, headRef }) {
  return (
    <group ref={headRef} position={[0, y, -0.02]}>
      {/* Neck */}
      <mesh position={[0, -0.16, 0]}>
        <cylinderGeometry args={[0.045, 0.055, 0.1, 10]} />
        <meshStandardMaterial color={skin} roughness={0.7} />
      </mesh>
      {/* Head — softly oval, natural skin */}
      <mesh castShadow scale={[0.95, 1.08, 1.02]}>
        <sphereGeometry args={[0.155, 24, 24]} />
        <meshStandardMaterial color={skin} roughness={0.65} />
      </mesh>
      {/* Ears */}
      {[-0.15, 0.15].map((x, i) => (
        <mesh key={i} position={[x, 0.01, 0]}>
          <sphereGeometry args={[0.026, 10, 10]} />
          <meshStandardMaterial color={skin} roughness={0.6} />
        </mesh>
      ))}
      {/* Hair — four styles */}
      {hairStyle === 0 && (
        <>
          <mesh position={[0, 0.06, -0.02]}>
            <sphereGeometry args={[0.158, 18, 14, 0, Math.PI * 2, 0, Math.PI * 0.58]} />
            <meshStandardMaterial color={hair} roughness={0.9} />
          </mesh>
          <mesh position={[0, 0.1, -0.06]}>
            <boxGeometry args={[0.28, 0.03, 0.11]} />
            <meshStandardMaterial color={hair} roughness={0.9} />
          </mesh>
        </>
      )}
      {hairStyle === 1 && (
        <mesh position={[0, 0.055, -0.02]}>
          <sphereGeometry args={[0.16, 18, 14, 0, Math.PI * 2, 0, Math.PI * 0.62]} />
          <meshStandardMaterial color={hair} roughness={0.9} />
        </mesh>
      )}
      {hairStyle === 2 && (
        <>
          <mesh position={[0, 0.06, -0.02]}>
            <sphereGeometry args={[0.158, 18, 14, 0, Math.PI * 2, 0, Math.PI * 0.58]} />
            <meshStandardMaterial color={hair} roughness={0.9} />
          </mesh>
          <mesh position={[0, 0.17, 0.05]}>
            <sphereGeometry args={[0.058, 12, 10]} />
            <meshStandardMaterial color={hair} roughness={0.9} />
          </mesh>
        </>
      )}
      {hairStyle === 3 && (
        <>
          <mesh position={[0, 0.055, -0.02]}>
            <sphereGeometry args={[0.158, 18, 14, 0, Math.PI * 2, 0, Math.PI * 0.58]} />
            <meshStandardMaterial color={hair} roughness={0.9} />
          </mesh>
          {[[-0.11, 0.09, -0.05], [0.11, 0.08, -0.04], [0, 0.13, -0.07]].map(([hx, hy, hz], i) => (
            <mesh key={i} position={[hx, hy, hz]}>
              <sphereGeometry args={[0.042, 10, 8]} />
              <meshStandardMaterial color={hair} roughness={0.9} />
            </mesh>
          ))}
        </>
      )}
      {/* Eyes — sclera + pupil, brows */}
      {[-0.05, 0.05].map((x, i) => (
        <group key={i}>
          <mesh position={[x, 0.015, -0.135]}>
            <sphereGeometry args={[0.021, 10, 8]} />
            <meshStandardMaterial color="#f0efe9" roughness={0.25} />
          </mesh>
          <mesh position={[x, 0.015, -0.144]}>
            <sphereGeometry args={[0.011, 10, 8]} />
            <meshStandardMaterial color="#221a12" roughness={0.15} />
          </mesh>
          <mesh position={[x, 0.062, -0.132]}>
            <boxGeometry args={[0.03, 0.006, 0.01]} />
            <meshStandardMaterial color={hair} roughness={0.9} />
          </mesh>
        </group>
      ))}
      {/* Nose + mouth */}
      <mesh position={[0, 0.02, -0.148]}>
        <boxGeometry args={[0.016, 0.026, 0.012]} />
        <meshStandardMaterial color={skin} roughness={0.7} />
      </mesh>
      <mesh position={[0, -0.055, -0.132]}>
        <boxGeometry args={[0.034, 0.009, 0.01]} />
        <meshStandardMaterial color="#a96a4a" roughness={0.7} />
      </mesh>
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   WORKER — seated humanoid, per-agent skin/hair variation.
   Faces the monitor (-z); typing arms + breathing + slight lean, driven by
   status. Two-segment arms (sleeve + bare forearm/hand) for a more human look.
   ══════════════════════════════════════════════════════════════════════════════ */
export function Worker({ color, status, variant, position }) {
  const groupRef = useRef(null)
  const bodyRef = useRef(null)
  const headRef = useRef(null)
  const leftArmRef = useRef(null)
  const rightArmRef = useRef(null)
  const state = status === 'working' ? 'working' : status === 'done' ? 'done' : status === 'error' ? 'error' : 'idle'

  const skin = useMemo(() => new THREE.Color(SKINS[variant % SKINS.length]), [variant])
  const hair = useMemo(() => new THREE.Color(HAIRS[variant % HAIRS.length]), [variant])
  const shirt = useMemo(() => toColor(color).multiplyScalar(0.68), [color])
  const pants = useMemo(() => new THREE.Color(variant % 2 === 0 ? '#2e2e38' : '#26262e'), [variant])
  const hairStyle = variant % 4

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const g = groupRef.current
    if (!g) return

    // ── Per-state posture: idle is upright, working leans in, done sits back, error slumps ──
    let lean = -0.02
    let headPitch = 0.06
    let headRoll = 0.035
    let armBase = 1.02
    let armAmp = 0.05
    let armFreq = 1.6
    let breatheFreq = 1.3
    let glance = Math.sin(t * 0.33) * 0.22 + Math.sin(t * 1.1) * 0.06
    let extraHeadYaw = 0
    let weightShift = 0.012

    if (state === 'working') {
      lean = -0.085
      headPitch = 0.16
      headRoll = 0.02
      armBase = 1.16
      breatheFreq = 2.4
      weightShift = 0.008
      // Typing bursts — arms speed up, then pause on the keyboard, then resume
      const gate = Math.max(0.08, Math.sin(t * 0.8) * 0.5 + 0.5)
      armAmp = 0.22 * gate
      armFreq = 10 + Math.sin(t * 0.7) * 1.5
      // Occasional glance away from the screen
      extraHeadYaw = Math.max(0, Math.sin(t * 0.23 + 2) - 0.7) * 0.32
    } else if (state === 'done') {
      lean = 0.05
      weightShift = 0.015
      armBase = 0.74
      armAmp = 0.03
      armFreq = 1.1
      breatheFreq = 1.1
      glance = Math.sin(t * 0.3) * 0.12
      // Occasional satisfied nod
      headPitch = 0.04 + Math.max(0, Math.sin(t * 0.5)) * 0.14
    } else if (state === 'error') {
      lean = 0.1
      headPitch = 0.24
      headRoll = 0.02
      weightShift = 0.006
      armBase = 0.55
      armAmp = 0.02
      armFreq = 0.7
      breatheFreq = 0.9
      glance = Math.sin(t * 0.22) * 0.06
    }

    // Breathing
    g.position.y = Math.sin(t * breatheFreq) * 0.005
    // Body — lean + slow weight shift, never frozen
    if (bodyRef.current) {
      bodyRef.current.rotation.x = lean + Math.sin(t * 0.8) * 0.012
      bodyRef.current.rotation.z = Math.sin(t * 0.25) * 0.02 + Math.sin(t * 0.35) * weightShift
    }
    // Head — screen focus while working, wandering glance idle, nod when done
    if (headRef.current) {
      headRef.current.rotation.x = headPitch + Math.sin(t * 3.5) * (state === 'working' ? 0.04 : 0.02)
      headRef.current.rotation.y = glance + extraHeadYaw
      headRef.current.rotation.z = Math.sin(t * 1.15 + 1.2) * headRoll
    }
    // Arms — typing hands (slightly asymmetric speed), resting otherwise
    if (leftArmRef.current) {
      leftArmRef.current.rotation.x = armBase + Math.sin(t * armFreq) * armAmp * 0.5
    }
    if (rightArmRef.current) {
      rightArmRef.current.rotation.x = armBase + 0.02 + Math.sin(t * armFreq * 0.93 + 1.7) * armAmp * 0.5
    }
  })

  return (
    <group ref={groupRef} position={position || [0, 0, 0]}>
      {/* Legs — proper seated pose: thighs forward, shins down, feet planted */}
      {[-0.11, 0.11].map((x, i) => (
        <group key={`leg${i}`}>
          {/* Thigh — hip (on the seat) to knee */}
          <mesh position={[x, 0.56, -0.1]} rotation-x={1.05} castShadow>
            <capsuleGeometry args={[0.06, 0.26, 4, 8]} />
            <meshStandardMaterial color={pants} roughness={0.85} />
          </mesh>
          {/* Shin — knee down to the floor */}
          <mesh position={[x, 0.29, -0.24]} rotation-x={-0.08} castShadow>
            <capsuleGeometry args={[0.05, 0.24, 4, 8]} />
            <meshStandardMaterial color={pants} roughness={0.85} />
          </mesh>
          {/* Foot */}
          <mesh position={[x, 0.07, -0.21]} castShadow>
            <boxGeometry args={[0.1, 0.055, 0.17]} />
            <meshStandardMaterial color="#23232c" roughness={0.6} />
          </mesh>
        </group>
      ))}
      {/* Torso — pelvis rests on the chair seat */}
      <group ref={bodyRef} position={[0, 0.6, 0]}>
        {/* Pelvis */}
        <mesh position={[0, 0, 0]} castShadow>
          <boxGeometry args={[0.34, 0.2, 0.26]} />
          <meshStandardMaterial color={shirt} roughness={0.85} />
        </mesh>
        {/* Waist — smooths the pelvis→chest transition */}
        <mesh position={[0, 0.19, -0.02]} castShadow>
          <cylinderGeometry args={[0.15, 0.17, 0.22, 12]} />
          <meshStandardMaterial color={shirt} roughness={0.85} />
        </mesh>
        {/* Chest — rounded, natural taper */}
        <mesh position={[0, 0.39, -0.03]} castShadow scale={[1, 0.88, 0.62]}>
          <sphereGeometry args={[0.27, 22, 16]} />
          <meshStandardMaterial color={shirt} roughness={0.85} />
        </mesh>
        {/* Shoulders — rounded */}
        {[-0.21, 0.21].map((x, i) => (
          <mesh key={i} position={[x, 0.56, -0.03]} castShadow>
            <sphereGeometry args={[0.115, 14, 12]} />
            <meshStandardMaterial color={shirt} roughness={0.85} />
          </mesh>
        ))}
        {/* Collar accent */}
        <mesh position={[0, 0.59, -0.03]}>
          <boxGeometry args={[0.24, 0.045, 0.17]} />
          <meshStandardMaterial color={color} metalness={0.3} roughness={0.5} transparent opacity={0.75} />
        </mesh>
        {/* Arms — two-segment, hinge at the shoulder, hands reach the keyboard */}
        <group ref={leftArmRef} position={[-0.25, 0.56, -0.03]}>
          <mesh position={[0, -0.13, 0.06]} castShadow>
            <capsuleGeometry args={[0.062, 0.22, 4, 10]} />
            <meshStandardMaterial color={shirt} roughness={0.85} />
          </mesh>
          <group position={[0, -0.27, 0.16]} rotation-x={0.4}>
            <mesh position={[0, -0.1, 0.05]} castShadow>
              <capsuleGeometry args={[0.052, 0.16, 4, 10]} />
              <meshStandardMaterial color={shirt} roughness={0.85} />
            </mesh>
            <mesh position={[0, -0.19, 0.07]} castShadow>
              <sphereGeometry args={[0.048, 10, 8]} />
              <meshStandardMaterial color={skin} roughness={0.7} />
            </mesh>
          </group>
        </group>
        <group ref={rightArmRef} position={[0.25, 0.56, -0.03]}>
          <mesh position={[0, -0.13, 0.06]} castShadow>
            <capsuleGeometry args={[0.062, 0.22, 4, 10]} />
            <meshStandardMaterial color={shirt} roughness={0.85} />
          </mesh>
          <group position={[0, -0.27, 0.16]} rotation-x={0.4}>
            <mesh position={[0, -0.1, 0.05]} castShadow>
              <capsuleGeometry args={[0.052, 0.16, 4, 10]} />
              <meshStandardMaterial color={shirt} roughness={0.85} />
            </mesh>
            <mesh position={[0, -0.19, 0.07]} castShadow>
              <sphereGeometry args={[0.048, 10, 8]} />
              <meshStandardMaterial color={skin} roughness={0.7} />
            </mesh>
          </group>
        </group>
        {/* Head group — face at -z (toward the monitor); sits just above the screen */}
        <WorkerHead skin={skin} hair={hair} hairStyle={hairStyle} y={0.9} headRef={headRef} />
      </group>
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   STANDING WORKER — upright figure used while walking/hovering between desks.
   Legs + arms swing while walking for a natural gait.
   ══════════════════════════════════════════════════════════════════════════════ */
export function StandingWorker({ color, variant, walking }) {
  const groupRef = useRef(null)
  const bodyRef = useRef(null)
  const headRef = useRef(null)
  const legLRef = useRef(null)
  const legRRef = useRef(null)
  const armLRef = useRef(null)
  const armRRef = useRef(null)

  const skin = useMemo(() => new THREE.Color(SKINS[variant % SKINS.length]), [variant])
  const hair = useMemo(() => new THREE.Color(HAIRS[variant % HAIRS.length]), [variant])
  const shirt = useMemo(() => toColor(color).multiplyScalar(0.68), [color])
  const pants = useMemo(() => new THREE.Color(variant % 2 === 0 ? '#2e2e38' : '#26262e'), [variant])
  const hairStyle = variant % 4

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const g = groupRef.current
    if (!g) return
    const s = Math.sin(t * 9.5)
    if (walking) {
      // Footstep bob + forward lean + upper-body counter-roll with each stride
      g.position.y = Math.abs(Math.sin(t * 9.5)) * 0.04
      if (legLRef.current) legLRef.current.rotation.x = s * 0.5
      if (legRRef.current) legRRef.current.rotation.x = -s * 0.5
      if (armLRef.current) armLRef.current.rotation.x = -0.15 - s * 0.3
      if (armRRef.current) armRRef.current.rotation.x = -0.15 + s * 0.3
      if (bodyRef.current) {
        bodyRef.current.rotation.x = -0.12
        bodyRef.current.rotation.z = Math.cos(t * 9.5) * 0.04
      }
      if (headRef.current) {
        headRef.current.rotation.x = 0.05 + Math.sin(t * 9.5) * 0.03
        headRef.current.rotation.y = Math.sin(t * 0.4) * 0.08
      }
    } else {
      // Hovering / standing still — breathing, weight shift, idle glance around
      g.position.y = Math.sin(t * 1.2) * 0.006
      if (legLRef.current) legLRef.current.rotation.x = 0
      if (legRRef.current) legRRef.current.rotation.x = 0
      if (armLRef.current) armLRef.current.rotation.x = -0.06 + Math.sin(t * 0.7 + 1) * 0.03
      if (armRRef.current) armRRef.current.rotation.x = -0.06 + Math.sin(t * 0.7 + 4) * 0.03
      if (bodyRef.current) {
        bodyRef.current.rotation.x = -0.03 + Math.sin(t * 1.2) * 0.008
        bodyRef.current.rotation.z = Math.sin(t * 0.6) * 0.025
      }
      if (headRef.current) {
        headRef.current.rotation.x = 0.03 + Math.sin(t * 0.9) * 0.02
        headRef.current.rotation.y = Math.sin(t * 0.32) * 0.25 + Math.sin(t * 1.3) * 0.07
        headRef.current.rotation.z = Math.sin(t * 0.8 + 2) * 0.03
      }
    }
  })

  return (
    <group ref={groupRef}>
      {/* Legs */}
      {[-0.11, 0.11].map((x, i) => (
        <group key={i} ref={i === 0 ? legLRef : legRRef} position={[x, 0.55, 0]}>
          <mesh castShadow>
            <capsuleGeometry args={[0.055, 0.78, 4, 8]} />
            <meshStandardMaterial color={pants} roughness={0.85} />
          </mesh>
          <mesh position={[0, -0.49, 0.03]} castShadow>
            <boxGeometry args={[0.1, 0.07, 0.17]} />
            <meshStandardMaterial color="#23232c" roughness={0.6} />
          </mesh>
        </group>
      ))}
      <group ref={bodyRef}>
        {/* Pelvis */}
        <mesh position={[0, 1.0, -0.02]} castShadow>
          <boxGeometry args={[0.32, 0.2, 0.24]} />
          <meshStandardMaterial color={pants} roughness={0.85} />
        </mesh>
        {/* Waist — smooths the pelvis→chest transition */}
        <mesh position={[0, 1.11, -0.02]} castShadow>
          <cylinderGeometry args={[0.15, 0.17, 0.2, 12]} />
          <meshStandardMaterial color={shirt} roughness={0.85} />
        </mesh>
        {/* Chest */}
        <mesh position={[0, 1.22, -0.02]} castShadow scale={[1, 0.88, 0.62]}>
          <sphereGeometry args={[0.27, 22, 16]} />
          <meshStandardMaterial color={shirt} roughness={0.85} />
        </mesh>
        {/* Shoulders */}
        {[-0.21, 0.21].map((x, i) => (
          <mesh key={i} position={[x, 1.38, -0.02]} castShadow>
            <sphereGeometry args={[0.115, 14, 12]} />
            <meshStandardMaterial color={shirt} roughness={0.85} />
          </mesh>
        ))}
        {/* Collar accent */}
        <mesh position={[0, 1.42, -0.02]}>
          <boxGeometry args={[0.24, 0.045, 0.17]} />
          <meshStandardMaterial color={color} metalness={0.3} roughness={0.5} transparent opacity={0.75} />
        </mesh>
        {/* Arms — relaxed, hanging */}
        <group ref={armLRef} position={[-0.25, 1.38, 0.02]}>
          <mesh position={[0, -0.18, 0]} castShadow>
            <capsuleGeometry args={[0.062, 0.28, 4, 10]} />
            <meshStandardMaterial color={shirt} roughness={0.85} />
          </mesh>
          <group position={[0, -0.4, 0]} rotation-x={0.12}>
            <mesh position={[0, -0.1, 0]} castShadow>
              <capsuleGeometry args={[0.052, 0.18, 4, 10]} />
              <meshStandardMaterial color={shirt} roughness={0.85} />
            </mesh>
            <mesh position={[0, -0.22, 0.02]} castShadow>
              <sphereGeometry args={[0.048, 10, 8]} />
              <meshStandardMaterial color={skin} roughness={0.7} />
            </mesh>
          </group>
        </group>
        <group ref={armRRef} position={[0.25, 1.38, 0.02]}>
          <mesh position={[0, -0.18, 0]} castShadow>
            <capsuleGeometry args={[0.062, 0.28, 4, 10]} />
            <meshStandardMaterial color={shirt} roughness={0.85} />
          </mesh>
          <group position={[0, -0.4, 0]} rotation-x={0.12}>
            <mesh position={[0, -0.1, 0]} castShadow>
              <capsuleGeometry args={[0.052, 0.18, 4, 10]} />
              <meshStandardMaterial color={shirt} roughness={0.85} />
            </mesh>
            <mesh position={[0, -0.22, 0.02]} castShadow>
              <sphereGeometry args={[0.048, 10, 8]} />
              <meshStandardMaterial color={skin} roughness={0.7} />
            </mesh>
          </group>
        </group>
        <WorkerHead skin={skin} hair={hair} hairStyle={hairStyle} y={1.66} headRef={headRef} />
      </group>
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   MOBILE WORKER — an avatar driven by a single `choreo` command:
     • {kind:'called'}  from the staff area → walk to the supervisor's office,
                        hover (receive the assignment), then walk on to the desk.
     • {kind:'report'}  from the desk → walk to the supervisor's office, hover
                        (report back), then walk back to the staff area.
     • {kind:'rest'}    walk to the staff area (its initial home) and stand there.
     • {kind:'desk'}    walk back to the desk and sit.
     • null             stay put (seated at the desk, or standing at the staff area).
   Workers mount at their staff-centre stall (in front of the break-room
   counter) and idle there standing until a command arrives; the supervisor
   (no stall) stays put seated at its office. New commands are ignored while a
   walk/hover is in progress — the parent re-issues after onSeated/onArrived
   resolves.
   ══════════════════════════════════════════════════════════════════════════════ */
export function MobileWorker({ choreo, restFacing, color, status, variant, seatedFacing, home, keyName, onSeated, onArrived }) {
  const groupRef = useRef(null)
  const parked = !!STAFF_HOME[keyName] // has a staff-centre stall → idles standing there (supervisor stays seated)
  const [pose, setPose] = useState(parked ? 'standing' : 'seated')
  const [walking, setWalking] = useState(false)
  const phaseRef = useRef(parked ? 'atRest' : 'seated') // 'seated' | 'atRest' | 'walking' | 'hover'
  const pathRef = useRef([])
  const destRef = useRef('desk')
  const segRef = useRef(0)
  const distRef = useRef(0)
  const hoverTRef = useRef(0)
  const faceRef = useRef(parked ? restFacing : seatedFacing)
  const reportRef = useRef(false) // hovering for a report (short check-in) vs receiving an assignment
  const effectiveWalkSpeed = keyName === TEST_GLTF_AGENT ? 1.6 : WALK_SPEED
  // Workers mount at their staff-centre stall (in front of the break-room
  // counter) and idle there standing until a command arrives; the supervisor
  // (no stall) stays put at its home. Only read at mount — the walking loop
  // takes over.
  const initialHome = STAFF_HOME[keyName] || home

  const arrive = useCallback(() => {
    const g = groupRef.current
    if (!g) return
    if (destRef.current === 'supervisor') {
      // At the supervisor's office door — hover, facing the supervisor.
      phaseRef.current = 'hover'
      hoverTRef.current = 0
      setWalking(false)
      faceRef.current = faceDir(g.position, v3(SUPERVISOR.pos.x, SUPERVISOR.pos.z))
    } else if (destRef.current === 'rest') {
      phaseRef.current = 'atRest'
      setPose('standing')
      setWalking(false)
      faceRef.current = restFacing
      if (onArrived) onArrived(keyName)
    } else {
      phaseRef.current = 'seated'
      setPose('seated')
      setWalking(false)
      faceRef.current = seatedFacing
      if (onSeated) onSeated(keyName)
    }
  }, [keyName, onArrived, onSeated, restFacing, seatedFacing])

  const startChoreo = useCallback((cmd) => {
    const g = groupRef.current
    if (!g) return
    // Snapshot the start position — pathTo* embeds it as path[0], and the
    // walking loop lerpVectors() writes into g.position every frame. If we
    // passed the live object, mutating g.position would silently drag path[0]
    // forward too, collapsing the first segment (the "instant slip").
    const from = g.position.clone()
    const kind = cmd.kind
    reportRef.current = cmd.kind === 'report'
    pathRef.current = kind === 'rest' ? pathToRest(from, cmd.target)
      : kind === 'desk' ? pathToDesk(from, keyName)
      : pathToSupervisor(from, keyName)
    destRef.current = kind === 'rest' ? 'rest' : kind === 'desk' ? 'desk' : 'supervisor'
    if (pathRef.current.length < 2) { arrive(); return }
    phaseRef.current = 'walking'
    segRef.current = 0
    distRef.current = 0
    setPose('standing')
    setWalking(true)
    faceRef.current = faceDir(pathRef.current[0], pathRef.current[1])
  }, [arrive, keyName])

  // Start a command whenever the worker is idle (seated or at rest).
  useEffect(() => {
    if (!choreo) return
    if (phaseRef.current === 'seated' || phaseRef.current === 'atRest') startChoreo(choreo)
  }, [choreo, startChoreo])

  useFrame((_, dt) => {
    const g = groupRef.current
    if (!g) return
    const phase = phaseRef.current

    if (phase === 'walking') {
      const path = pathRef.current
      let rem = dt * effectiveWalkSpeed
      while (rem > 0 && segRef.current < path.length - 1) {
        const a = path[segRef.current]
        const b = path[segRef.current + 1]
        const len = a.distanceTo(b)
        if (len === 0) { segRef.current += 1; continue }
        const d = distRef.current + rem
        if (d >= len) {
          rem -= len - distRef.current
          distRef.current = 0
          segRef.current += 1
        } else {
          distRef.current = d
          rem = 0
        }
        const t = Math.min(1, distRef.current / len)
        g.position.lerpVectors(a, b, t)
        faceRef.current = faceDir(a, b)
      }
      if (segRef.current >= path.length - 1) {
        g.position.copy(path[path.length - 1])
        arrive()
      }
    } else if (phase === 'hover') {
      hoverTRef.current += dt * 1000
      if (hoverTRef.current >= (reportRef.current ? REPORT_LEG_MS : HOVER_MS)) {
        // clone() again: path[0] must be a snapshot, not the live position
        // that gets lerp-mutated for the next segment.
        if (reportRef.current) {
          // Report done — head back to the staff centre (its initial home).
          pathRef.current = pathToRest(g.position.clone(), STAFF_HOME[keyName])
          destRef.current = 'rest'
        } else {
          // Assignment received — walk on to the desk and sit down.
          pathRef.current = pathToDesk(g.position.clone(), keyName)
          destRef.current = 'desk'
        }
        if (pathRef.current.length < 2) { arrive(); return }
        segRef.current = 0
        distRef.current = 0
        phaseRef.current = 'walking'
        setWalking(true)
        faceRef.current = faceDir(pathRef.current[0], pathRef.current[1])
      }
    } else if (phase === 'atRest') {
      // Gently turn toward the counter — or a chatty neighbour — if the seat
      // assignment changed while standing here.
      let diff = restFacing - faceRef.current
      diff = Math.atan2(Math.sin(diff), Math.cos(diff))
      faceRef.current += diff * Math.min(1, dt * 2.5)
    }

    g.rotation.y = faceRef.current
  })

  return (
    <group ref={groupRef} position={initialHome}>
      {keyName === TEST_GLTF_AGENT ? (
        <GLTFAvatar walking={walking} seated={pose === 'seated'} scale={1} yOffset={0} />
      ) : pose === 'seated' ? (
        <Worker color={color} status={status} variant={variant} />
      ) : (
        <StandingWorker color={color} variant={variant} walking={walking} />
      )}
    </group>
  )
}
