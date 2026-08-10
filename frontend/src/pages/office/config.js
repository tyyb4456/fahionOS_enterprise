// frontend/src/pages/office/config.js
import { SOURCE_META } from '../chat/constants'

// True RGB used for three.js materials (var(--gold) is only usable in CSS).
export const GOLD3 = '#d4d4d8'

// Floor-plan coordinates. +z is toward the camera (front of the office),
// -z is toward the back where the CEO/supervisor corner office sits.
// `rot` is the yaw of the station so desks face the right direction.
// Layout (open plan):
//   • Supervisor — top-center, its own glass office (z=-11).
//   • Three desk pods below it: Demand (Research+Sales, left),
//     Ops (Supplier+Inventory, middle), Growth (Finance+Marketing, right).
//     Within each pod the two desks face each other across a short aisle.
//   • Break room — a full-width strip at the bottom (+z).

export const OFFICE_POS = {
  supervisor: { x: 0, z: -11, rot: 0 },

  // Demand pod (left) — customer / market-facing side.
  research_agent:  { x: -9.35, z: -2.5, rot: -Math.PI / 2 },
  sales_agent:     { x: -6.65, z: -2.5, rot: Math.PI / 2 },

  // Ops pod (middle) — procurement / stock side.
  supplier_agent:  { x: -1.35, z: -2.5, rot: -Math.PI / 2 },
  inventory_agent: { x: 1.35,  z: -2.5, rot: Math.PI / 2 },

  // Growth pod (right) — revenue / brand side.
  finance_agent:   { x: 6.65,  z: -2.5, rot: -Math.PI / 2 },
  marketing_agent: { x: 9.35,  z: -2.5, rot: Math.PI / 2 },
}

export const AGENT_ROLES = {
  inventory_agent: 'Operations',
  sales_agent:     'Revenue & Growth',
  marketing_agent: 'Brand & Marketing',
  finance_agent:   'Finance',
  research_agent:  'Market Intelligence',
  supplier_agent:  'Procurement',
}

export const AGENT_ORDER = Object.keys(SOURCE_META).filter(k => k !== 'main agent')

export function agentMeta(key) {
  const meta = SOURCE_META[key] || { label: key, color: '#94a3b8' }
  const pos = OFFICE_POS[key] || { x: 0, z: 0, rot: 0 }
  return { key, label: meta.label, color: meta.color, role: AGENT_ROLES[key] || 'Team', pos, rot: pos.rot || 0 }
}

export const SUPERVISOR = {
  key: 'supervisor',
  label: 'Supervisor',
  role: 'Chief Executive Agent',
  color: GOLD3,
  pos: OFFICE_POS.supervisor,
}

export const STATUS_LABEL = {
  idle: 'Online · Idle',
  working: 'Working',
  done: 'Finished',
  error: 'Failed',
}
