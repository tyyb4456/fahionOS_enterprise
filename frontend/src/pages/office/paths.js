// frontend/src/pages/office/paths.js
// Floor-plan routing + movement helpers shared by the choreography and the
// worker avatars: the walkway network (front aisle z=-1 + back aisle z=-4 +
// middle corridor x=0), the walled staff-stall nook at the back, and per-agent
// home / supervisor visit spots.
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

// Staff break area — a visible strip between the kitchen counter (front at
// z≈5.6) and the desk pods / front aisle (z=-1). Every worker idles here
// standing until dispatched to the supervisor's office, and returns here to
// idle after reporting back. Each agent's spot is fixed and held for the whole
// session, so the idle crowd stays put instead of reshuffling between runs.
export const BREAK_HOME = {}
// Per-agent idle facing (yaw). 0 = facing -z (into the office), π = facing +z
// (back wall). Angled values create the look of chatting pairs/trios.
export const BREAK_FACING = {}
{
  // Natural break-room layout — not a line! Small clusters scattered around
  // the counter front, like real coworkers on a coffee break.
  //
  //  ┌─── counter (z≈5.95) ──────────────────────────────────────────────┐
  //  │  [0]+[1] chatting     [2] solo       [3]+[4] chatting    [5] solo │
  //  │   near cooler          by stools      near bistro       by plant  │
  //  └──────────────────────────────────────────────────────────────────┘
  //
  const spots = [
    // — Left pair chatting near the water cooler —
    { x: -6.8,  z: 6.8,  yaw:  0.35 },  // agent 0: angled right (toward agent 1)
    { x: -5.2,  z: 6.3,  yaw: -0.3  },  // agent 1: angled left (toward agent 0)
    // — Solo agent leaning near a stool —
    { x: -1.6,  z: 7.0,  yaw:  0.15 },  // agent 2: mostly facing room, slight glance
    // — Pair chatting near the bistro table area —
    { x:  2.2,  z: 6.4,  yaw:  0.4  },  // agent 3: angled right (toward agent 4)
    { x:  4.0,  z: 6.9,  yaw: -0.5  },  // agent 4: angled left (toward agent 3)
    // — Solo agent standing by the plant, looking around —
    { x:  7.2,  z: 6.5,  yaw: -0.2  },  // agent 5: slight leftward glance
  ]
  AGENT_ORDER.forEach((key, i) => {
    const s = spots[i] || spots[0]
    BREAK_HOME[key] = v3(s.x, s.z)
    BREAK_FACING[key] = s.yaw
  })
}

// Legacy walled nook at the back of the office — no longer used for idle
// placement (agents now idle in the front break area) but still consulted by
// the walkway router for points that end up inside it.
const NOOK_X_MIN = -7.7
const NOOK_X_MAX = -5.3
const NOOK_Z_MIN = -8.6
const NOOK_Z_MAX = -4.6
export const inNook = (p) => p.x <= NOOK_X_MAX && p.x >= NOOK_X_MIN && p.z <= NOOK_Z_MAX && p.z >= NOOK_Z_MIN

// Home spot where each worker idles while no task is assigned. The supervisor
// has no stall — it stays seated at its office.
export const STAFF_HOME = (key) => (key === 'supervisor' ? null : BREAK_HOME[key])
// Per-worker idle facing — uses the hand-placed yaw from BREAK_FACING above,
// with a tiny per-session jitter so repeated reloads aren't pixel-identical.
const sessionFacings = new Map()
export const STAFF_FACING = (key) => {
  if (!sessionFacings.has(key)) {
    const base = BREAK_FACING[key] || 0
    sessionFacings.set(key, base + (Math.random() - 0.5) * 0.15)
  }
  return sessionFacings.get(key)
}

export const supSeat = () => v3(SUPERVISOR.pos.x, SUPERVISOR.pos.z - 1.35)
export const agentSeat = (key) => { const a = agentMeta(key); return v3(a.pos.x + Math.sin(a.rot) * SEAT_Z, a.pos.z + Math.cos(a.rot) * SEAT_Z) }
// Standing spot just in front of the supervisor's glass office door, slightly
// offset per agent so parallel reports don't stack on the same tile.
export const supVisitSpot = (key) => v3(SUPERVISOR.pos.x + (AGENT_ORDER.indexOf(key) % 3 - 1) * 0.6, SUPERVISOR.pos.z + 2.3)

// Point-to-point routes through the walkway network (never through desks).
// Desk legs always hop onto the front aisle first (never cut through a pod),
// then walk up to the desk's approach point and into the seat.
// Consecutive-duplicate cleanup — the nook exit/entry prefixes can introduce
// repeated knots after a detour.
const dedupe = (pts) => pts.filter((p, i) => i === 0 || p.distanceTo(pts[i - 1]) > 1e-4)

// A worker leaving the break area (or the legacy nook) routes to the front
// aisle, then down the x=0 corridor. The break area sits in front of the
// kitchen counter (z > 5.2); workers walk through the counter gap (at x≈0)
// to reach the desk-side walkway network.
const COUNTER_GAP_X = 0     // center of the gap between counter halves
const COUNTER_Z = 5.2       // z just behind the counter (desk-side)
function exitStaffCenter(from) {
  if (inNook(from)) {
    // Legacy nook: back-aisle detour to the middle corridor.
    return {
      pts: [from, v3(from.x, AISLE_Z), v3(0, AISLE_Z), v3(0, FRONT_AISLE_Z)],
      p: v3(0, FRONT_AISLE_Z),
    }
  }
  // Break area (in front of counter, z > COUNTER_Z): walk to the gap, through
  // it, then to the front aisle.
  if (from.z > COUNTER_Z) {
    return {
      pts: [from, v3(COUNTER_GAP_X, from.z), v3(COUNTER_GAP_X, FRONT_AISLE_Z)],
      p: v3(COUNTER_GAP_X, FRONT_AISLE_Z),
    }
  }
  // Already on the desk side of the counter — step to the front aisle.
  return {
    pts: [from, v3(from.x, FRONT_AISLE_Z), v3(0, FRONT_AISLE_Z)],
    p: v3(0, FRONT_AISLE_Z),
  }
}

export function pathToSupervisor(from, key) {
  const spot = supVisitSpot(key)
  const { pts, p } = exitStaffCenter(from)
  from = p
  if (from.z < -6) return dedupe([...pts, from, spot])
  return dedupe([...pts, v3(from.x, FRONT_AISLE_Z), v3(0, FRONT_AISLE_Z), spot])
}
export function pathToDesk(from, key) {
  const seat = agentSeat(key)
  const approach = deskApproach(key)
  const { pts, p } = exitStaffCenter(from)
  from = p
  if (from.distanceTo(seat) < 0.15) return dedupe([...pts, seat])
  if (from.z < -6) return dedupe([...pts, v3(0, FRONT_AISLE_Z), v3(seat.x, FRONT_AISLE_Z), approach, seat])
  return dedupe([...pts, v3(from.x, FRONT_AISLE_Z), v3(seat.x, FRONT_AISLE_Z), approach, seat])
}
export function pathToRest(from, target) {
  if (from.distanceTo(target) < 0.15) return [from]
  const { pts, p } = exitStaffCenter(from)
  from = p
  let out
  if (inNook(target)) {
    // Legacy nook: enter from the front via corridor → back aisle → north mouth.
    out = [...pts, v3(from.x, FRONT_AISLE_Z), v3(0, FRONT_AISLE_Z), v3(0, AISLE_Z), v3(target.x, AISLE_Z), target]
  } else if (target.z > COUNTER_Z) {
    // Target is in the break area (in front of counter): route through the gap
    // at x=0 to cross the counter, then walk to the target spot.
    out = [...pts, v3(from.x, FRONT_AISLE_Z), v3(COUNTER_GAP_X, FRONT_AISLE_Z), v3(COUNTER_GAP_X, target.z), target]
  } else if (from.z < -6) {
    // Coming from deep in office (supervisor / back desks): corridor → front aisle → target.
    out = [...pts, v3(0, FRONT_AISLE_Z), v3(target.x, FRONT_AISLE_Z), target]
  } else {
    // Coming from front aisle area: step to front aisle → target.x → target.
    out = [...pts, v3(from.x, FRONT_AISLE_Z), v3(target.x, FRONT_AISLE_Z), target]
  }
  return dedupe(out)
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

// Round the interior corners of a walkway polyline with small fillets so the
// walkers trace smooth curves instead of snapping 90° at each knot. The radius
// (~0.28) is tiny next to the aisle->furniture clearance (0.45), so even the
// inward sag of a 90° fillet (0.414 * r ≈ 0.12) never reaches a desk edge.
// Corners that are essentially straight are left untouched. Returns a densified
// list: start point, every corner's arc samples, end point.
export function roundPath(path, r = 0.28, step = 0.07) {
  if (path.length < 3) return path
  const out = [path[0].clone()]
  for (let i = 1; i < path.length - 1; i++) {
    const b = path[i], p = path[i - 1], q = path[i + 1]
    const u1 = new THREE.Vector3().subVectors(b, p)
    const u2 = new THREE.Vector3().subVectors(q, b)
    const d1 = u1.length(), d2 = u2.length()
    if (d1 < 1e-4 || d2 < 1e-4) { out.push(b.clone()); continue }
    u1.normalize(); u2.normalize()
    const cosT = u1.dot(u2)
    if (cosT > 0.9999) { out.push(b.clone()); continue } // near-straight, no fillet
    const rr = Math.min(r, d1 / 3, d2 / 3)
    const t1 = b.clone().addScaledVector(u1, rr)
    const t2 = b.clone().addScaledVector(u2, rr)
    const bis = u1.clone().add(u2)
    if (bis.lengthSq() < 1e-6) { out.push(b.clone()); continue } // U-turn, keep the knot
    bis.normalize()
    const sinHalf = Math.sqrt(Math.max(0, (1 - cosT) / 2))
    const center = b.clone().addScaledVector(bis, rr / Math.max(1e-6, sinHalf))
    const v1 = t1.clone().sub(center), v2 = t2.clone().sub(center)
    const a1 = Math.atan2(v1.z, v1.x)
    let sweep = Math.atan2(v2.z, v2.x) - a1
    sweep = Math.atan2(Math.sin(sweep), Math.cos(sweep)) // signed, short direction
    const n = Math.max(1, Math.ceil((Math.abs(sweep) * rr) / step))
    for (let k = 1; k <= n; k++) {
      const a = a1 + sweep * (k / n)
      out.push(center.clone().add(new THREE.Vector3(Math.cos(a) * rr, 0, Math.sin(a) * rr)))
    }
  }
  out.push(path[path.length - 1].clone())
  return out
}
