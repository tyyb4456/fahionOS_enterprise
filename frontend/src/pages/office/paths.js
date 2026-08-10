// frontend/src/pages/office/paths.js
// Floor-plan routing + movement helpers shared by the choreography and the
// worker avatars: the walkway network (aisle z=-4 + middle corridor x=0),
// the fixed break-room seats, and per-agent home / supervisor visit spots.
import * as THREE from 'three'
import { agentMeta, AGENT_ORDER, SUPERVISOR } from './config'

export const WALK_SPEED = 3.0
export const HOVER_MS = 2600
export const SEAT_Z = 0.45
// The pods sit at z=-2.5 with a clear walkway behind them (z=-4) leading up the
// middle corridor (x=0) to the supervisor's office, which opens at z≈-9.3.
export const AISLE_Z = -4.0
export const v3 = (x, z) => new THREE.Vector3(x, 0, z)
export const faceDir = (a, b) => Math.atan2(-(b.x - a.x), -(b.z - a.z))
// Fixed break-room seats around the bar counter (world coords), x-sorted for
// adjacency. The first three match the rendered bar stools (z=6.75); the rest
// are standing spots along the counter front (z=6.3), clear of the water
// cooler (-7.3), bistro table (3.4/7.6) and plant (7.7). All face the counter,
// i.e. -z (yaw 0).
export const BAR_SEATS = [
  v3(-5.0, 6.3),
  v3(-1.2, 6.75),
  v3(0, 6.75),
  v3(1.2, 6.75),
  v3(5.0, 6.3),
  v3(6.6, 6.3),
]

export const supSeat = () => v3(SUPERVISOR.pos.x, SUPERVISOR.pos.z - 1.35)
export const agentSeat = (key) => { const a = agentMeta(key); return v3(a.pos.x + Math.sin(a.rot) * SEAT_Z, a.pos.z + Math.cos(a.rot) * SEAT_Z) }
// Standing spot just in front of the supervisor's glass office door, slightly
// offset per agent so parallel reports don't stack on the same tile.
export const supVisitSpot = (key) => v3(SUPERVISOR.pos.x + (AGENT_ORDER.indexOf(key) % 3 - 1) * 0.6, SUPERVISOR.pos.z + 2.3)

// Point-to-point routes through the walkway network (never through desks).
export function pathToSupervisor(from, key) {
  const spot = supVisitSpot(key)
  if (from.z >= 0.5) return [from, v3(0, from.z), v3(0, AISLE_Z), spot]
  if (from.z < -6) return [from, spot]
  return [from, v3(from.x, AISLE_Z), v3(0, AISLE_Z), spot]
}
export function pathToDesk(from, key) {
  const seat = agentSeat(key)
  if (from.distanceTo(seat) < 0.15) return [from]
  if (from.z >= 0.5) return [from, v3(0, from.z), v3(0, AISLE_Z), v3(seat.x, AISLE_Z), seat]
  if (from.z < -6) return [from, v3(0, AISLE_Z), v3(seat.x, AISLE_Z), seat]
  return [from, v3(from.x, AISLE_Z), v3(seat.x, AISLE_Z), seat]
}
export function pathToRest(from, target) {
  if (from.distanceTo(target) < 0.15) return [from]
  if (from.z < -6) return [from, v3(0, AISLE_Z), v3(0, target.z), target]
  return [from, target]
}

// Stable home positions (shared, never re-created) so seated workers actually
// sit on their chairs instead of piling up at the world origin.
export const SUP_HOME = supSeat()
export const AGENT_HOME = {}
AGENT_ORDER.forEach(key => { AGENT_HOME[key] = agentSeat(key) })
