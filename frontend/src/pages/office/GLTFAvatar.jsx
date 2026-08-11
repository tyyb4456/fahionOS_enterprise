// frontend/src/pages/office/GLTFAvatar.jsx
import { useEffect, useMemo, useRef } from 'react'
import { useGLTF, useAnimations } from '@react-three/drei'
import { clone as cloneSkeleton } from 'three/examples/jsm/utils/SkeletonUtils.js'

const MODEL_PATH = '/models/avatar.glb'

export function GLTFAvatar({
  walking,
  seated = false,
  scale = 1,
  yOffset = 0,
  facingOffset = Math.PI,
  // [x, y, z] nudge applied only while seated. Measured from avatar.glb
  // (typed pose): the baked Hips sit at glb (0.002, 0.481, 0.010) and the
  // fingertips at z 0.55–0.60, so once the avatar is parked on the chair —
  // origin at the seat, station z = 0.45 − glb.z + seatOffset.z — the oy=0.06
  // lands the pelvis on the cushion (0.555, a natural ~1.5 cm sink) and
  // oz=0.14 brings the fingertips to station z ≈ 0.05, exactly where the
  // repositioned keyboard lives. The furniture (keyboard/mouse) is moved to
  // the hands, not the other way round.
  seatOffset = [0, 0.06, 0.14],
  walkTimeScale = 0.7,         // leg cadence for Walking only; Idle/Typing untouched since those looked fine
}) {
  const group = useRef(null)
  const { scene, animations } = useGLTF(MODEL_PATH)
  const clone = useMemo(() => cloneSkeleton(scene), [scene])
  const { actions } = useAnimations(animations, group)
  // Drive the clips through a ref: the mutation-based useAnimations API
  // (reset/timeScale/fadeIn/fadeOut) trips the react-hooks/immutability rule
  // when the returned `actions` object is touched after render. Holding it in
  // a ref is the sanctioned escape hatch, and it keeps the clip effect stable
  // even if useAnimations returns a new actions object across renders.
  const actionsRef = useRef(actions)
  useEffect(() => {
    actionsRef.current = actions
  })
  const currentRef = useRef(null)

  useEffect(() => {
    // While seated, always use the seated Typing loop — the standing Idle clip
    // would straighten the legs straight through the chair. The standing Idle
    // is only correct at the break room / waiting around.
    const name = walking ? 'Walking' : (seated ? 'Typing' : 'Idle')
    if (currentRef.current === name) return
    currentRef.current = name

    const action = actionsRef.current[name]
    if (!action) {
      console.warn(`GLTFAvatar: no clip named "${name}" — available:`, Object.keys(actionsRef.current))
      return
    }
    action.reset()
    action.timeScale = name === 'Walking' ? walkTimeScale : 1
    action.fadeIn(0.3).play()
    return () => action.fadeOut(0.3)
  }, [walking, seated, walkTimeScale])

  const [ox, oy, oz] = seated ? seatOffset : [0, 0, 0]

  return (
    <group ref={group} position={[ox, yOffset + oy, oz]} rotation={[0, facingOffset, 0]} scale={scale}>
      <primitive object={clone} />
    </group>
  )
}

useGLTF.preload(MODEL_PATH)