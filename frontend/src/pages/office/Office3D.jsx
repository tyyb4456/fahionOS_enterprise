// frontend/src/pages/office/Office3D.jsx
// Virtual AI Office - 3D environment. Renders the room shell, break room and
// all the furniture (desks, chairs, monitors, lamps, supervisor office) with
// shared lighting. No characters, no movement, no comms — environment only.
import { forwardRef, useImperativeHandle, useRef } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { GOLD3, OFFICE_POS } from './config'
import { Room, BreakRoom } from './environment'
import { GlassWalls, RoundDesk, Desk, OfficeChair } from './furniture'

const DESK_KEYS = Object.keys(OFFICE_POS).filter(k => k !== 'supervisor')

/* ══════════════════════════════════════════════════════════════════════════════
   MAIN SCENE — environment-only render
   ══════════════════════════════════════════════════════════════════════════════ */
function OfficeScene({ isMobile, controlsRef }) {
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
      <group position={[OFFICE_POS.supervisor.x, 0, OFFICE_POS.supervisor.z]}>
        <GlassWalls />
        <RoundDesk color={GOLD3} status="idle" selected={false} />
        {/* Executive chair behind the round desk, facing the team */}
        <group position={[0, 0, -1.35]} rotation-y={Math.PI}>
          <OfficeChair />
        </group>
      </group>

      {DESK_KEYS.map(key => {
        const pos = OFFICE_POS[key]
        return (
          <group key={key} position={[pos.x, 0, pos.z]} rotation-y={pos.rot}>
            <Desk color={GOLD3} status="idle" selected={false} />
            <OfficeChair />
          </group>
        )
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
const Office3D = forwardRef(function Office3D({ isMobile }, ref) {
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
        isMobile={isMobile}
        controlsRef={controlsRef}
      />
    </Canvas>
  )
})

export default Office3D