// frontend/src/pages/office/config.js

// True RGB used for three.js materials (var(--gold) is only usable in CSS).
export const GOLD3 = '#d4d4d8'

// Floor-plan coordinates. +z is toward the camera (front of the office),
// -z is toward the back where the CEO/supervisor corner office sits.
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