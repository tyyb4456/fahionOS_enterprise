// frontend/src/pages/office/furniture.jsx
// Desks, office chairs, monitors, task lamps and the supervisor glass office.
import * as THREE from 'three'
import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { GOLD3 } from './config'
import { M } from './materials'

export function StatusLight({ color, status, selected, radius = 1.25 }) {
  const matRef = useRef(null)
  const active = status === 'working' || status === 'done' || status === 'error'
  const ringColor = status === 'done' ? '#22c55e' : status === 'error' ? '#ef4444' : color

  useFrame(({ clock }) => {
    const mat = matRef.current
    if (!mat) return
    const t = clock.getElapsedTime()
    if (status === 'working') {
      mat.color.set(ringColor)
      mat.opacity = 0.32 + 0.18 * Math.sin(t * 4)
    } else if (active) {
      mat.color.set(ringColor)
      mat.opacity = 0.3
    } else {
      mat.color.set('#33333c')
      mat.opacity = 0.14
    }
    if (selected) mat.opacity = Math.max(mat.opacity, 0.7)
  })

  return (
    <mesh rotation-x={-Math.PI / 2} position={[0, 0.012, 0]}>
      <torusGeometry args={[radius, 0.02, 8, 64]} />
      <meshBasicMaterial ref={matRef} transparent toneMapped={false} />
    </mesh>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   MONITOR — slim monitor on a stand with a glowing screen + power LED
   Screen faces +z (toward the camera) so the working glow reads clearly.
   ══════════════════════════════════════════════════════════════════════════════ */
export function Monitor({ color, status, selected }) {
  const screenRef = useRef(null)
  const working = status === 'working'

  useFrame(({ clock }) => {
    const mat = screenRef.current
    if (!mat) return
    if (working) {
      mat.emissive.set(color)
      mat.emissiveIntensity = 0.9 + 0.3 * Math.sin(clock.getElapsedTime() * 5)
      mat.color.set('#0e1020')
    } else if (status === 'error') {
      mat.emissive.set('#ef4444')
      mat.emissiveIntensity = 0.4
      mat.color.set('#160a0a')
    } else if (selected) {
      mat.emissive.set(GOLD3)
      mat.emissiveIntensity = 0.45
      mat.color.set('#14120e')
    } else {
      mat.emissive.set('#274063')
      mat.emissiveIntensity = 0.5
      mat.color.set('#0b0e18')
    }
  })

  const mw = 1.3
  const mh = 0.72
  return (
    <group position={[0, 0, -0.12]}>
      {/* Panel — raised so the screen reads clear of seated heads */}
      <group position={[0, 1.22, -0.15]} rotation-x={-0.06}>
        {/* Bezel */}
        <mesh castShadow>
          <boxGeometry args={[mw + 0.06, mh + 0.06, 0.035]} />
          <meshStandardMaterial color="#22222c" metalness={0.4} roughness={0.5} />
        </mesh>
        {/* Screen */}
        <mesh position={[0, 0, 0.02]}>
          <planeGeometry args={[mw, mh]} />
          <meshStandardMaterial ref={screenRef} color="#0b0e18" emissive="#274063" emissiveIntensity={0.5} toneMapped={false} />
        </mesh>
        {/* Desktop UI lines while working */}
        {working && (
          <group position={[0, 0, 0.023]}>
            <mesh position={[0, mh * 0.3, 0]}>
              <planeGeometry args={[mw * 0.86, 0.035]} />
              <meshBasicMaterial color={color} transparent opacity={0.35} toneMapped={false} />
            </mesh>
            {[-0.04, 0.05, 0.14].map((y, i) => (
              <mesh key={i} position={[-mw * 0.12, y, 0]}>
                <planeGeometry args={[mw * (0.42 + i * 0.14), 0.02]} />
                <meshBasicMaterial color="#ffffff" transparent opacity={0.12 + i * 0.05} toneMapped={false} />
              </mesh>
            ))}
          </group>
        )}
        {/* Power LED */}
        <mesh position={[0, -mh / 2 - 0.02, 0.02]}>
          <circleGeometry args={[0.011, 12]} />
          <meshBasicMaterial color={working ? color : status === 'error' ? '#ef4444' : '#4a4a5a'} toneMapped={false} />
        </mesh>
      </group>
      {/* Stand */}
      <mesh position={[0, 0.92, -0.15]} castShadow>
        <boxGeometry args={[0.05, 0.26, 0.05]} />
        <meshStandardMaterial color={M.metal} metalness={0.6} roughness={0.35} />
      </mesh>
      <mesh position={[0, 0.79, -0.15]} castShadow>
        <cylinderGeometry args={[0.13, 0.15, 0.025, 20]} />
        <meshStandardMaterial color={M.metal} metalness={0.6} roughness={0.35} />
      </mesh>
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   KEYBOARD + MOUSE
   Positioned so the seated characters' hands land on them. Both the procedural
   Worker and the GLTF mocap avatar type with their hands at station z ≈ 0.05,
   y ≈ 0.83 (the seat sits 0.45 in front of the desk origin) — so the board is
   pulled up near the desk's front edge (desk-local z 0.32 → station 0.00),
   raised slightly to key height, and the mouse sits just right of the keys.
   ══════════════════════════════════════════════════════════════════════════════ */
export function Peripherals() {
  return (
    <group position={[0, 0.8, 0.32]}>
      <mesh castShadow>
        <boxGeometry args={[0.6, 0.02, 0.2]} />
        <meshStandardMaterial color="#262630" metalness={0.3} roughness={0.6} />
      </mesh>
      {[-0.05, 0.01, 0.07].map((z, i) => (
        <mesh key={i} position={[0, 0.012, z]}>
          <boxGeometry args={[0.54, 0.005, 0.04]} />
          <meshStandardMaterial color="#3a3a46" roughness={0.7} />
        </mesh>
      ))}
      {/* Sized up and lightened — the old color nearly matched the desk
          laminate and disappeared against it. */}
      <mesh castShadow position={[0.34, 0.033, 0.34]}>
        <capsuleGeometry args={[0.04, 0.05, 4, 10]} />
        <meshStandardMaterial color="#55555f" metalness={0.3} roughness={0.45} />
      </mesh>
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   TASK LAMP — emissive shade, warm pool of light
   ══════════════════════════════════════════════════════════════════════════════ */
export function TaskLamp({ color, status }) {
  const shadeRef = useRef(null)
  const working = status === 'working'

  useFrame(({ clock }) => {
    const mat = shadeRef.current
    if (!mat) return
    mat.emissiveIntensity = working ? 1.6 + 0.2 * Math.sin(clock.getElapsedTime() * 2) : 0.9
  })

  return (
    <group position={[-0.7, 0.78, -0.28]}>
      <mesh position={[0, -0.05, 0]}>
        <cylinderGeometry args={[0.055, 0.065, 0.02, 12]} />
        <meshStandardMaterial color="#1a1a22" metalness={0.6} roughness={0.4} />
      </mesh>
      <mesh position={[0, 0.18, 0]} rotation-x={0.15}>
        <cylinderGeometry args={[0.012, 0.012, 0.3, 6]} />
        <meshStandardMaterial color="#20202a" metalness={0.6} roughness={0.4} />
      </mesh>
      <mesh position={[0, 0.34, 0.05]} rotation-x={-0.4}>
        <coneGeometry args={[0.07, 0.09, 14, 1, true]} />
        <meshStandardMaterial ref={shadeRef} color="#14141c" emissive={color} emissiveIntensity={1.4} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   DESK — laminate top, drawer pedestal, modesty panel, back panel
   ══════════════════════════════════════════════════════════════════════════════ */
export function Desk({ color, status, selected }) {
  const dw = 2.1
  const dd = 0.95
  const dh = 0.74
  return (
    <group position={[0, 0, -0.32]}>
      {/* Top */}
      <mesh position={[0, dh, 0]} castShadow receiveShadow>
        <boxGeometry args={[dw, 0.055, dd]} />
        <meshStandardMaterial color={M.laminate} metalness={0.15} roughness={0.55} />
      </mesh>
      {/* Edge accent */}
      <mesh position={[0, dh + 0.028, dd / 2 - 0.005]}>
        <boxGeometry args={[dw - 0.06, 0.012, 0.02]} />
        <meshStandardMaterial color={color} metalness={0.5} roughness={0.4} transparent opacity={0.5} />
      </mesh>
      {/* Modesty panel */}
      <mesh position={[0, dh / 2 - 0.06, -dd / 2 + 0.03]} castShadow>
        <boxGeometry args={[dw * 0.8, dh * 0.42, 0.02]} />
        <meshStandardMaterial color={M.panel} roughness={0.85} />
      </mesh>
      {/* Drawer pedestal (right side) */}
      <group position={[dw / 2 - 0.34, 0, 0]}>
        <mesh position={[0, dh * 0.42, 0]} castShadow>
          <boxGeometry args={[0.56, dh * 0.84, dd * 0.7]} />
          <meshStandardMaterial color={M.panel} roughness={0.8} />
        </mesh>
        {[0.14, 0.02].map((dy, i) => (
          <mesh key={i} position={[0, dh * 0.42 + dy, dd * 0.35 + 0.01]}>
            <boxGeometry args={[0.2, 0.018, 0.02]} />
            <meshStandardMaterial color={M.metalHi} metalness={0.7} roughness={0.3} />
          </mesh>
        ))}
      </group>
      {/* Legs */}
      {[[-dw / 2 + 0.08, dd / 2 - 0.08], [dw / 2 - 0.08, dd / 2 - 0.08], [-dw / 2 + 0.08, -dd / 2 + 0.08]].map(([x, z], i) => (
        <mesh key={i} position={[x, dh / 2 - 0.03, z]} castShadow>
          <boxGeometry args={[0.05, dh - 0.05, 0.05]} />
          <meshStandardMaterial color={M.metal} metalness={0.6} roughness={0.4} />
        </mesh>
      ))}
      {/* Monitor + peripherals + lamp on top */}
      <Monitor color={color} status={status} selected={selected} />
      <Peripherals />
      <TaskLamp color={color} status={status} />
      {/* Nameplate */}
      <group position={[dw / 2 - 0.55, dh + 0.04, -dd / 2 + 0.14]}>
        <mesh>
          <boxGeometry args={[0.34, 0.035, 0.09]} />
          <meshStandardMaterial color={M.black} metalness={0.4} roughness={0.5} />
        </mesh>
        <mesh position={[0, 0.02, 0]}>
          <boxGeometry args={[0.3, 0.005, 0.07]} />
          <meshStandardMaterial color={color} metalness={0.6} roughness={0.3} />
        </mesh>
      </group>
      {/* Coffee mug on the front-left */}
      <group position={[-0.62, dh + 0.028, 0.34]}>
        <mesh castShadow>
          <cylinderGeometry args={[0.035, 0.032, 0.09, 14]} />
          <meshStandardMaterial color="#3d3d48" roughness={0.6} />
        </mesh>
        <mesh position={[0, 0.046, 0]}>
          <cylinderGeometry args={[0.038, 0.038, 0.012, 14]} />
          <meshStandardMaterial color="#4a4a58" metalness={0.4} roughness={0.5} />
        </mesh>
      </group>
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   OFFICE CHAIR — five-star caster base, gas lift, seat, backrest, armrests
   ══════════════════════════════════════════════════════════════════════════════ */
export function OfficeChair() {
  return (
    <group position={[0, 0, 0.45]}>
      {/* Caster base */}
      <mesh position={[0, 0.035, 0]}>
        <cylinderGeometry args={[0.3, 0.3, 0.03, 6]} />
        <meshStandardMaterial color="#3a3a48" metalness={0.7} roughness={0.3} />
      </mesh>
      {Array.from({ length: 6 }).map((_, i) => {
        const a = (i / 6) * Math.PI * 2
        return (
          <mesh key={i} position={[Math.cos(a) * 0.26, 0.03, Math.sin(a) * 0.26]}>
            <sphereGeometry args={[0.025, 8, 8]} />
            <meshStandardMaterial color="#2a2a34" metalness={0.7} roughness={0.4} />
          </mesh>
        )
      })}
      {/* Gas lift — reaches the seat */}
      <mesh position={[0, 0.27, 0]}>
        <cylinderGeometry args={[0.03, 0.045, 0.46, 10]} />
        <meshStandardMaterial color="#4a4a5c" metalness={0.7} roughness={0.3} />
      </mesh>
      {/* Seat — cushion sits on a slightly larger base */}
      <mesh position={[0, 0.53, 0]} castShadow>
        <boxGeometry args={[0.54, 0.05, 0.5]} />
        <meshStandardMaterial color={M.fabric} roughness={0.9} />
      </mesh>
      <mesh position={[0, 0.57, 0]} castShadow>
        <boxGeometry args={[0.48, 0.03, 0.46]} />
        <meshStandardMaterial color="#55556a" roughness={0.9} />
      </mesh>
      {/* Backrest — behind the seated worker (local +z), gently reclined */}
      <mesh position={[0, 0.9, 0.24]} rotation-x={0.05} castShadow>
        <boxGeometry args={[0.48, 0.62, 0.055]} />
        <meshStandardMaterial color={M.fabric} roughness={0.9} />
      </mesh>
      <mesh position={[0, 1.2, 0.25]} rotation-x={0.05}>
        <boxGeometry args={[0.4, 0.035, 0.07]} />
        <meshStandardMaterial color={GOLD3} metalness={0.6} roughness={0.35} transparent opacity={0.5} />
      </mesh>
      {/* Armrests */}
      {[-0.26, 0.26].map((x, i) => (
        <group key={i} position={[x, 0.72, 0]}>
          <mesh>
            <boxGeometry args={[0.035, 0.3, 0.035]} />
            <meshStandardMaterial color={M.metal} metalness={0.6} roughness={0.4} />
          </mesh>
          <mesh position={[0, 0.16, 0]}>
            <boxGeometry args={[0.055, 0.025, 0.16]} />
            <meshStandardMaterial color="#4c4c5a" roughness={0.75} />
          </mesh>
        </group>
      ))}
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   WORKER HEAD — shared by seated and walking avatars (hair, face, neck)
   ══════════════════════════════════════════════════════════════════════════════ */
export function GlassWalls() {
  const wallH = 2.1
  const t = 0.05
  const w = 4.6
  const d = 3.8
  const glass = { color: '#7a90ad', transparent: true, opacity: 0.22, metalness: 0.85, roughness: 0.12 }

  return (
    <group position={[0, wallH / 2, -0.15]}>
      {[-w / 2, w / 2].map((x, i) => (
        <group key={i} position={[x, 0, 0]}>
          <mesh castShadow>
            <boxGeometry args={[t, wallH, d]} />
            <meshStandardMaterial {...glass} />
          </mesh>
          <mesh position={[t / 2 + 0.005, 0, 0]}>
            <boxGeometry args={[0.01, wallH, d]} />
            <meshStandardMaterial color={GOLD3} transparent opacity={0.08} metalness={0.8} roughness={0.2} />
          </mesh>
          <mesh position={[0, wallH / 2, 0]}>
            <boxGeometry args={[t + 0.04, 0.05, d + 0.03]} />
            <meshStandardMaterial color={GOLD3} metalness={0.8} roughness={0.2} transparent opacity={0.7} />
          </mesh>
        </group>
      ))}
      <mesh position={[0, 0, -d / 2]} castShadow>
        <boxGeometry args={[w, wallH, t]} />
        <meshStandardMaterial {...glass} />
      </mesh>
      <mesh position={[0, wallH / 2, -d / 2]}>
        <boxGeometry args={[w + 0.03, 0.05, t + 0.04]} />
        <meshStandardMaterial color={GOLD3} metalness={0.8} roughness={0.2} transparent opacity={0.7} />
      </mesh>
    </group>
  )
}

/* ROUND EXECUTIVE DESK — circular top for the CEO's corner office.
   Two monitors face the CEO (who sits at the -z side, looking out +z). */
export function RoundDesk({ color, status, selected }) {
  const r = 1.0
  return (
    <group>
      {/* Top */}
      <mesh position={[0, 0.74, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[r, r, 0.055, 36]} />
        <meshStandardMaterial color={M.laminate} metalness={0.15} roughness={0.55} />
      </mesh>
      {/* Rim accent */}
      <mesh position={[0, 0.745, 0]}>
        <cylinderGeometry args={[r + 0.012, r + 0.012, 0.014, 36]} />
        <meshStandardMaterial color={color} metalness={0.5} roughness={0.4} transparent opacity={0.6} />
      </mesh>
      {/* Pedestal + base */}
      <mesh position={[0, 0.38, 0]} castShadow>
        <cylinderGeometry args={[0.4, 0.5, 0.76, 24]} />
        <meshStandardMaterial color={M.panel} roughness={0.8} />
      </mesh>
      <mesh position={[0, 0.03, 0]} castShadow>
        <cylinderGeometry args={[0.8, 0.9, 0.06, 24]} />
        <meshStandardMaterial color={M.metal} metalness={0.6} roughness={0.4} />
      </mesh>
      {/* Two monitors on the front arc, facing the CEO (-z) */}
      {[-0.55, 0.55].map((x, i) => (
        <group key={i} position={[x, 0, 0.3]} rotation-y={Math.PI}>
          <Monitor color={color} status={status} selected={selected} />
        </group>
      ))}
      {/* Keyboard + mouse on the CEO's side */}
      <group position={[0, 0, -0.55]}>
        <Peripherals />
      </group>
      {/* Coffee mug + paper stack */}
      <mesh position={[0.5, 0.775, -0.15]}>
        <cylinderGeometry args={[0.045, 0.04, 0.07, 14]} />
        <meshStandardMaterial color="#8a4a2a" roughness={0.6} />
      </mesh>
      <mesh position={[-0.55, 0.79, 0.1]}>
        <boxGeometry args={[0.22, 0.05, 0.3]} />
        <meshStandardMaterial color="#d8d4c8" roughness={0.85} />
      </mesh>
      <mesh position={[-0.55, 0.83, 0.1]}>
        <boxGeometry args={[0.18, 0.035, 0.26]} />
        <meshStandardMaterial color="#efead9" roughness={0.85} />
      </mesh>
    </group>
  )
}

