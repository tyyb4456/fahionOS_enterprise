// frontend/src/pages/office/environment.jsx
// The room shell: carpet floor, walls, skyline windows, pendant rails and
// the break room (counter, stools, bistro table, plants).
import { useMemo } from 'react'
import * as THREE from 'three'
import { GOLD3 } from './config'

/* ══════════════════════════════════════════════════════════════════════════════
   CARPET TEXTURE — canvas-generated carpet tiles (base + grout + speckle noise)
   ══════════════════════════════════════════════════════════════════════════════ */
function makeCarpetTexture() {
  const size = 256
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')
  ctx.fillStyle = '#26262d'
  ctx.fillRect(0, 0, size, size)
  // Tile grout lines — 4×4 tiles of 64px
  ctx.strokeStyle = '#1c1c23'
  ctx.lineWidth = 5
  for (let i = 0; i <= 4; i++) {
    ctx.beginPath(); ctx.moveTo(i * 64, 0); ctx.lineTo(i * 64, size); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(0, i * 64); ctx.lineTo(size, i * 64); ctx.stroke()
  }
  // Subtle carpet speckle noise
  for (let i = 0; i < 5000; i++) {
    const x = Math.random() * size
    const y = Math.random() * size
    const v = Math.random()
    ctx.fillStyle = v > 0.5 ? `rgba(255,255,255,${(v - 0.5) * 0.05})` : `rgba(0,0,0,${(0.5 - v) * 0.07})`
    ctx.fillRect(x, y, 1, 1)
  }
  const tex = new THREE.CanvasTexture(c)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  tex.repeat.set(22, 22)
  tex.anisotropy = 4
  return tex
}

/* ══════════════════════════════════════════════════════════════════════════════
   SKYLINE — canvas-generated night skyline for the windows
   ══════════════════════════════════════════════════════════════════════════════ */
function drawSkyline(ctx, w, h, color, winProb) {
  const floor = h - 8
  let x = 0
  while (x < w) {
    const bw = 26 + Math.random() * 22
    const bh = 40 + Math.random() * (h * 0.42)
    ctx.fillStyle = color
    ctx.fillRect(x, floor - bh, bw, bh)
    if (winProb > 0) {
      for (let wy = 0; wy < Math.floor(bh / 16); wy++) {
        for (let wx = 0; wx < 3; wx++) {
          if (Math.random() < winProb) {
            ctx.fillStyle = 'rgba(255,214,140,0.85)'
            ctx.fillRect(x + 6 + wx * 7, floor - bh + 8 + wy * 15, 4, 5)
            ctx.fillStyle = color
          }
        }
      }
    }
    x += bw + 3
  }
}
function makeSkylineTexture() {
  const w = 512
  const h = 256
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const ctx = c.getContext('2d')
  const g = ctx.createLinearGradient(0, 0, 0, h)
  g.addColorStop(0, '#0b1524')
  g.addColorStop(0.55, '#16263d')
  g.addColorStop(1, '#1e3047')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, w, h)
  for (let i = 0; i < 100; i++) {
    ctx.fillStyle = `rgba(255,255,255,${(Math.random() * 0.5).toFixed(2)})`
    ctx.fillRect(Math.floor(Math.random() * w), Math.floor(Math.random() * h * 0.55), 1, 1)
  }
  ctx.fillStyle = 'rgba(235,238,248,0.92)'
  ctx.beginPath(); ctx.arc(w * 0.78, h * 0.18, 11, 0, Math.PI * 2); ctx.fill()
  ctx.fillStyle = 'rgba(235,238,248,0.12)'
  ctx.beginPath(); ctx.arc(w * 0.78, h * 0.18, 24, 0, Math.PI * 2); ctx.fill()
  drawSkyline(ctx, w, h, '#101a2e', 0)
  drawSkyline(ctx, w, h, '#0a1220', 0.06)
  return new THREE.CanvasTexture(c)
}

function NightWindow({ position, width = 3.2, height = 1.8 }) {
  const tex = useMemo(() => makeSkylineTexture(), [])
  return (
    <group position={position}>
      <mesh castShadow>
        <boxGeometry args={[width + 0.14, height + 0.14, 0.07]} />
        <meshStandardMaterial color="#111116" roughness={0.6} metalness={0.5} />
      </mesh>
      <mesh position={[0, 0, 0.045]}>
        <planeGeometry args={[width, height]} />
        <meshBasicMaterial map={tex} toneMapped={false} />
      </mesh>
      <mesh position={[0, 0, 0.06]}>
        <boxGeometry args={[0.04, height, 0.015]} />
        <meshStandardMaterial color="#0d0d12" roughness={0.7} />
      </mesh>
      <mesh position={[0, 0, 0.06]}>
        <boxGeometry args={[width, 0.04, 0.015]} />
        <meshStandardMaterial color="#0d0d12" roughness={0.7} />
      </mesh>
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   BREAK ROOM — full-width kitchen strip at the front (+z): counter, water
   cooler, coffee machine, bar stools, bistro table, plant.
   ══════════════════════════════════════════════════════════════════════════════ */
export function BreakRoom() {
  return (
    <group position={[0, 0, 6.5]}>
      {/* Kitchen counter + lower cabinet */}
      <group position={[0, 0, -0.9]}>
        <mesh position={[0, 0.48, 0]} castShadow receiveShadow>
          <boxGeometry args={[16, 0.96, 0.7]} />
          <meshStandardMaterial color="#2e2e3a" roughness={0.8} />
        </mesh>
        <mesh position={[0, 0.95, 0]} castShadow>
          <boxGeometry args={[16, 0.05, 0.74]} />
          <meshStandardMaterial color="#4a4a5c" metalness={0.3} roughness={0.5} />
        </mesh>
        {[-6, -2, 2, 6].map(x => (
          <mesh key={x} position={[x, 0.55, 0.36]}>
            <boxGeometry args={[0.3, 0.025, 0.02]} />
            <meshStandardMaterial color={GOLD3} metalness={0.6} roughness={0.4} transparent opacity={0.6} />
          </mesh>
        ))}
      </group>
      {/* Coffee machine on the counter */}
      <group position={[-3.6, 1.0, -0.9]}>
        <mesh castShadow>
          <boxGeometry args={[0.36, 0.3, 0.26]} />
          <meshStandardMaterial color="#1c1c24" metalness={0.5} roughness={0.4} />
        </mesh>
        <mesh position={[0, 0.17, 0.14]}>
          <boxGeometry args={[0.2, 0.03, 0.02]} />
          <meshStandardMaterial color={GOLD3} metalness={0.7} roughness={0.3} transparent opacity={0.7} />
        </mesh>
      </group>
      {/* Kettle */}
      <mesh position={[-2.5, 1.0, -0.9]} castShadow>
        <cylinderGeometry args={[0.09, 0.07, 0.16, 12]} />
        <meshStandardMaterial color="#b8b8c4" metalness={0.7} roughness={0.3} />
      </mesh>
      {/* Fruit bowl */}
      <group position={[2.4, 1.0, -0.9]}>
        <mesh>
          <sphereGeometry args={[0.13, 12, 8, 0, Math.PI * 2, 0, Math.PI * 0.5]} />
          <meshStandardMaterial color="#3a3a46" roughness={0.6} />
        </mesh>
        <mesh position={[0, 0.06, 0]}>
          <sphereGeometry args={[0.055, 10, 8]} />
          <meshStandardMaterial color="#c0392b" roughness={0.4} />
        </mesh>
        <mesh position={[0.07, 0.05, 0.02]}>
          <sphereGeometry args={[0.05, 10, 8]} />
          <meshStandardMaterial color="#e67e22" roughness={0.4} />
        </mesh>
      </group>
      {/* Water cooler */}
      <group position={[-7.3, 0, -0.4]}>
        <mesh position={[0, 0.5, 0]} castShadow>
          <cylinderGeometry args={[0.18, 0.2, 1.0, 16]} />
          <meshStandardMaterial color="#3a3a48" roughness={0.6} />
        </mesh>
        <mesh position={[0, 1.05, 0]} castShadow>
          <cylinderGeometry args={[0.14, 0.16, 0.3, 16]} />
          <meshStandardMaterial color="#bcd4e8" transparent opacity={0.5} metalness={0.4} roughness={0.2} />
        </mesh>
        <mesh position={[0.16, 0.6, 0.12]} rotation-z={0.5}>
          <boxGeometry args={[0.06, 0.08, 0.05]} />
          <meshStandardMaterial color="#5a5a6a" metalness={0.5} roughness={0.4} />
        </mesh>
        <mesh position={[-0.16, 0.6, 0.12]} rotation-z={-0.5}>
          <boxGeometry args={[0.06, 0.08, 0.05]} />
          <meshStandardMaterial color="#5a5a6a" metalness={0.5} roughness={0.4} />
        </mesh>
      </group>
      {/* Bar stools in front of the counter */}
      {[[-1.2, 0], [0, 0], [1.2, 0]].map(([x, z], i) => (
        <group key={i} position={[x, 0, 0.25 + z]}>
          <mesh position={[0, 0.05, 0]}>
            <cylinderGeometry args={[0.02, 0.02, 0.6, 6]} />
            <meshStandardMaterial color="#343440" metalness={0.6} roughness={0.4} />
          </mesh>
          <mesh position={[0, 0.6, 0]}>
            <cylinderGeometry args={[0.24, 0.24, 0.06, 14]} />
            <meshStandardMaterial color="#3a3a48" roughness={0.9} />
          </mesh>
        </group>
      ))}
      {/* Rug under the bistro table */}
      <mesh rotation-x={-Math.PI / 2} position={[3.4, 0.001, 1.1]}>
        <circleGeometry args={[1.25, 24]} />
        <meshStandardMaterial color="#1e1e27" roughness={0.95} />
      </mesh>
      {/* Bistro table + chairs */}
      <group position={[3.4, 0, 1.1]}>
        <mesh position={[0, 0.75, 0]} castShadow>
          <cylinderGeometry args={[0.45, 0.45, 0.05, 18]} />
          <meshStandardMaterial color="#3e3e4a" metalness={0.3} roughness={0.5} />
        </mesh>
        <mesh position={[0, 0.37, 0]}>
          <cylinderGeometry args={[0.03, 0.03, 0.75, 8]} />
          <meshStandardMaterial color="#343440" metalness={0.6} roughness={0.4} />
        </mesh>
        {[[-0.65, 0], [0.65, 0]].map(([x, z], i) => (
          <group key={i} position={[x, 0, z]}>
            <mesh position={[0, 0.45, 0]}>
              <boxGeometry args={[0.42, 0.05, 0.42]} />
              <meshStandardMaterial color="#3a3a48" roughness={0.9} />
            </mesh>
            <mesh position={[0, 0.3, 0]}>
              <cylinderGeometry args={[0.02, 0.02, 0.45, 6]} />
              <meshStandardMaterial color="#343440" metalness={0.6} roughness={0.4} />
            </mesh>
            <mesh position={[0, 0.7, -0.21]}>
              <boxGeometry args={[0.4, 0.5, 0.04]} />
              <meshStandardMaterial color="#3a3a48" roughness={0.9} />
            </mesh>
          </group>
        ))}
      </group>
      {/* Plant */}
      <group position={[7.7, 0, -0.4]}>
        <mesh position={[0, 0.2, 0]} castShadow>
          <cylinderGeometry args={[0.2, 0.15, 0.4, 12]} />
          <meshStandardMaterial color="#5a4632" roughness={0.9} />
        </mesh>
        {[[0.16, 0.9, 0.1], [-0.14, 0.75, -0.1], [0.05, 1.1, -0.04]].map(([x, y, z], i) => (
          <mesh key={i} position={[x, y, z]} rotation-x={-0.5} rotation-z={i * 0.6}>
            <sphereGeometry args={[0.2, 8, 6, 0, Math.PI * 2, 0, Math.PI / 2]} />
            <meshStandardMaterial color="#2e4d2b" roughness={0.9} />
          </mesh>
        ))}
      </group>
    </group>
  )
}

/* ══════════════════════════════════════════════════════════════════════════════
   ROOM — carpet floor, walls, baseboards, skyline windows, pendant rails
   ══════════════════════════════════════════════════════════════════════════════ */
export function Room() {
  const carpet = useMemo(() => makeCarpetTexture(), [])
  return (
    <>
      {/* Carpet floor */}
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.02, 0]} receiveShadow>
        <planeGeometry args={[44, 44]} />
        <meshStandardMaterial map={carpet} roughness={0.92} />
      </mesh>

      {/* Back wall + baseboard */}
      <mesh position={[0, 3, -15.5]} receiveShadow>
        <planeGeometry args={[34, 7]} />
        <meshStandardMaterial color="#22222b" roughness={0.92} />
      </mesh>
      <mesh position={[0, 0.1, -15.28]}>
        <boxGeometry args={[34, 0.2, 0.08]} />
        <meshStandardMaterial color="#141418" roughness={0.7} />
      </mesh>
      {/* Side walls */}
      {[-16, 16].map((x, i) => (
        <group key={i}>
          <mesh position={[x, 3, -2]} rotation-y={i === 0 ? Math.PI / 2 : -Math.PI / 2} receiveShadow>
            <planeGeometry args={[30, 7]} />
            <meshStandardMaterial color="#26262f" roughness={0.92} />
          </mesh>
          <mesh position={[x, 0.1, -2]} rotation-y={i === 0 ? Math.PI / 2 : -Math.PI / 2}>
            <boxGeometry args={[30, 0.2, 0.08]} />
            <meshStandardMaterial color="#141418" roughness={0.7} />
          </mesh>
        </group>
      ))}

      {/* Skyline windows on the back wall */}
      <NightWindow position={[-6.4, 2.6, -15.28]} />
      <NightWindow position={[6.4, 2.6, -15.28]} />

      {/* Pendant rails — one over each pod, the office, and the break room */}
      {[-8, 0, 8].map(x => (
        <PendantRail key={x} x={x} z={-2.5} length={5.2} px={[-1.5, 0, 1.5]} />
      ))}
      <PendantRail x={0} z={-11} length={4} px={[-1.2, 1.2]} />
      <PendantRail x={0} z={6.5} length={16} px={[-6, -2, 2, 6]} />

      {/* Potted plants in the side aisles */}
      <group position={[-13.5, 0, -4]}>
        <mesh position={[0, 0.22, 0]} castShadow>
          <cylinderGeometry args={[0.22, 0.16, 0.44, 14]} />
          <meshStandardMaterial color="#5a4632" roughness={0.9} />
        </mesh>
        {[[0.18, 1.0, 0.12], [-0.16, 0.85, -0.12], [0.06, 1.25, -0.05]].map(([x, y, z], i) => (
          <mesh key={i} position={[x, y, z]} rotation-x={-0.5} rotation-z={i * 0.6}>
            <sphereGeometry args={[0.22, 8, 6, 0, Math.PI * 2, 0, Math.PI / 2]} />
            <meshStandardMaterial color="#2e4d2b" roughness={0.9} />
          </mesh>
        ))}
      </group>
      <group position={[13.5, 0, -4]}>
        <mesh position={[0, 0.22, 0]} castShadow>
          <cylinderGeometry args={[0.22, 0.16, 0.44, 14]} />
          <meshStandardMaterial color="#5a4632" roughness={0.9} />
        </mesh>
        {[[0.18, 1.0, 0.12], [-0.16, 0.85, -0.12], [0.06, 1.25, -0.05]].map(([x, y, z], i) => (
          <mesh key={i} position={[x, y, z]} rotation-x={-0.5} rotation-z={i * 0.6}>
            <sphereGeometry args={[0.22, 8, 6, 0, Math.PI * 2, 0, Math.PI / 2]} />
            <meshStandardMaterial color="#2e4d2b" roughness={0.9} />
          </mesh>
        ))}
      </group>
    </>
  )
}

function PendantRail({ x, z, length, px }) {
  return (
    <group position={[x, 3.3, z]}>
      <mesh>
        <boxGeometry args={[length, 0.12, 0.18]} />
        <meshStandardMaterial color="#1c1c22" metalness={0.7} roughness={0.3} />
      </mesh>
      {px.map((p, j) => (
        <group key={j} position={[p, -0.06, 0]}>
          <mesh position={[0, -0.18, 0]}>
            <cylinderGeometry args={[0.16, 0.2, 0.1, 16]} />
            <meshStandardMaterial color="#33333e" metalness={0.6} roughness={0.35} />
          </mesh>
          <mesh position={[0, -0.28, 0]}>
            <planeGeometry args={[0.5, 0.06]} />
            <meshBasicMaterial color="#fff6e0" transparent opacity={0.4} toneMapped={false} />
          </mesh>
        </group>
      ))}
    </group>
  )
}
