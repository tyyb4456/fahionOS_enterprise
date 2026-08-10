// frontend/src/pages/office/comms.jsx
// Communication layer: travelling packets between desks, faint connection
// lines and the pulsing active-status beams.
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'
import { AGENT_ORDER, agentMeta, SUPERVISOR } from './config'

/* ══════════════════════════════════════════════════════════════════════════════
   COMMUNICATION — travelling packets + faint connection lines + active beams
   ══════════════════════════════════════════════════════════════════════════════ */
const HEAD_Y = 1.7
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
export function TravelingPacket({ from, to, color }) {
  const ref = useRef(null)
  const geomRef = useRef(null)
  const progressRef = useRef(0)
  const start = useMemo(() => new THREE.Vector3(from[0], HEAD_Y, from[1]), [from])
  const end = useMemo(() => new THREE.Vector3(to[0], HEAD_Y, to[1]), [to])

  useFrame((_, dt) => {
    progressRef.current = Math.min(1, progressRef.current + dt / 0.85)
    const t = ease(progressRef.current)
    const p = start.clone().lerp(end, t)
    p.y += Math.sin(t * Math.PI) * 0.6
    if (ref.current) ref.current.position.copy(p)
    if (geomRef.current && geomRef.current.setFromPoints) {
      geomRef.current.setFromPoints([start.clone().lerp(end, Math.min(1, t * 1.4)), p])
      geomRef.current.attributes.position.needsUpdate = true
    }
  })

  return (
    <group>
      <mesh ref={ref}>
        <sphereGeometry args={[0.09, 14, 14]} />
        <meshBasicMaterial color={color} toneMapped={false} />
      </mesh>
      <line frustumCulled={false}>
        <bufferGeometry ref={geomRef} />
        <lineBasicMaterial color={color} transparent opacity={0.5} blending={THREE.AdditiveBlending} toneMapped={false} />
      </line>
    </group>
  )
}

export function ConnectionLines() {
  const points = AGENT_ORDER.map(key => {
    const a = agentMeta(key)
    return [SUPERVISOR.pos.x, HEAD_Y, SUPERVISOR.pos.z, a.pos.x, HEAD_Y, a.pos.z]
  })
  return (
    <group>
      {points.map(([sx, sy, sz, ax, ay, az], i) => (
        <line key={i} frustumCulled={false}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[new Float32Array([sx, sy, sz, ax, ay, az]), 3]} />
          </bufferGeometry>
          <lineBasicMaterial color="#3a3a46" transparent opacity={0.22} toneMapped={false} />
        </line>
      ))}
    </group>
  )
}

/* Active-status beams — a pulsing light link from the supervisor's desk to
   whichever agent is currently working (hub-and-spoke highlight). */
export function PulseLine({ from, to, color }) {
  const matRef = useRef(null)
  useFrame(({ clock }) => {
    if (matRef.current) matRef.current.opacity = 0.3 + 0.25 * (0.5 + 0.5 * Math.sin(clock.getElapsedTime() * 3))
  })
  return (
    <line frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[new Float32Array([...from, ...to]), 3]} />
      </bufferGeometry>
      <lineBasicMaterial ref={matRef} color={color} transparent opacity={0.5} blending={THREE.AdditiveBlending} toneMapped={false} />
    </line>
  )
}

export function ActiveBeams({ agents }) {
  const working = AGENT_ORDER.filter(key => (agents[key] || {}).status === 'working')
  return (
    <group>
      {working.map(key => {
        const a = agentMeta(key)
        return (
          <PulseLine
            key={key}
            from={[0, HEAD_Y, SUPERVISOR.pos.z]}
            to={[a.pos.x, HEAD_Y, a.pos.z]}
            color={a.color}
          />
        )
      })}
    </group>
  )
}

export function Pos({ x, z }) {
  return [x, z]
}
