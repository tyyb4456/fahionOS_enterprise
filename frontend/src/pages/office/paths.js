// frontend/src/pages/office/paths.js
// Floor-plan routing + movement helpers shared by the choreography and the
// worker avatars: the walkway network (front aisle z=-1 + middle corridor x=0),
// the staff-centre stalls, and per-agent home / supervisor visit spots.
import * as THREE from 'three'
import { agentMeta, AGENT_ORDER, OFFICE_POS, SUPERVISOR } from './config'

export const WALK_SPEED = 3.0
export const HOVER_MS = 2600
export const REPORT_LEG_MS = 1800 // supervisor check-in hover duration
export const SEAT_Z = 0.45
// Walkway network. The desk pods sit at z=-2.5; the front aisle (z=-1) runs
// along their fronts between the pods and the staff centre, the back aisle
// (z=-4) behind them, and the middle corridor (x=0) leads down to the
// supervisor's office (opens at z≈-9.3). The pod-gap aisle (x≈4) is the
// opening between the Ops pod and the Growth pod.
export const AISLE_Z = -4.0
export const FRONT_AISLE_Z = -1.0
export const POD_GAP_X = (OFFICE_POS.inventory_agent.x + OFFICE_POS.finance_agent.x) / 2
export const v3 = (x, z) => new THREE.Vector3(x, 0, z)
export const faceDir = (a, b) => Math.atan2(-(b.x - a.x), -(b.z - a.z))

// Staff centre — the open plaza directly in front of the break room. The
// break-room counter is a full-width strip (x∈[-8,8], z≈5.25..5.95), so the
// stalls sit on the office side of it (z≈3.25), clear of the counter, the
// bar stools, the water cooler and the bistro table. Every agent has a fixed
// stall where it idles when no task is assigned, spread across the width.
const STAFF_SPOTS = [
  v3(-7.0, 3.25),
  v3(-4.2, 3.25),
  v3(-1.4, 3.25),
  v3(1.4, 3.25),
  v3(4.2, 3.25),
  v3(7.0, 3.25),
]
export const STAFF_HOME = {}
AGENT_ORDER.forEach((key, i) => { STAFF_HOME[key] = STAFF_SPOTS[i % STAFF_SPOTS.length] })

export const supSeat = () => v3(SUPERVISOR.pos.x, SUPERVISOR.pos.z - 1.35)
export const agentSeat = (key) => { const a = agentMeta(key); return v3(a.pos.x + Math.sin(a.rot) * SEAT_Z, a.pos.z + Math.cos(a.rot) * SEAT_Z) }
// Standing spot just in front of the supervisor's glass office door, slightly
// offset per agent so parallel reports don't stack on the same tile.
export const supVisitSpot = (key) => v3(SUPERVISOR.pos.x + (AGENT_ORDER.indexOf(key) % 3 - 1) * 0.6, SUPERVISOR.pos.z + 2.3)

// Point-to-point routes through the walkway network (never through desks).
// Desk legs always hop onto the front aisle first (never cut through a pod),
// then walk up to the desk's approach point and into the seat.
export function pathToSupervisor(from, key) {
  const spot = supVisitSpot(key)
  if (from.z < -6) return [from, spot]
  if (from.z >= 0.5) return [from, v3(from.x, FRONT_AISLE_Z), v3(0, FRONT_AISLE_Z), spot]
  return [from, v3(from.x, FRONT_AISLE_Z), v3(0, FRONT_AISLE_Z), spot]
}
export function pathToDesk(from, key) {
  const seat = agentSeat(key)
  const approach = deskApproach(key)
  if (from.distanceTo(seat) < 0.15) return [from]
  if (from.z >= 0.5) return [from, v3(from.x, FRONT_AISLE_Z), v3(seat.x, FRONT_AISLE_Z), approach, seat]
  if (from.z < -6) return [from, v3(0, FRONT_AISLE_Z), v3(seat.x, FRONT_AISLE_Z), approach, seat]
  return [from, v3(from.x, FRONT_AISLE_Z), v3(seat.x, FRONT_AISLE_Z), approach, seat]
}
export function pathToRest(from, target) {
  if (from.distanceTo(target) < 0.15) return [from]
  if (from.z < -6) return [from, v3(0, FRONT_AISLE_Z), v3(target.x, FRONT_AISLE_Z), target]
  return [from, v3(from.x, FRONT_AISLE_Z), v3(target.x, FRONT_AISLE_Z), target]
}

// Stable home positions (shared, never re-created) so seated workers actually
// sit on their chairs instead of piling up at the world origin.
export const SUP_HOME = supSeat()
export const AGENT_HOME = {}
AGENT_ORDER.forEach(key => { AGENT_HOME[key] = agentSeat(key) })

// Approach point — 0.55 in front of the seat (along the desk's facing axis),
// on the aisle side. The worker walks to this tile, turns, and steps the last
// 0.55 into the chair before sitting. Never passes through the pod interior.
export const deskApproach = (key) => { const s = agentSeat(key); return v3(s.x, s.z + 0.55) }
