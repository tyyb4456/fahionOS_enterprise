import { Package, TrendingUp, Tag, Megaphone, FileText } from 'lucide-react'

export const GOLD     = 'var(--gold)'
export const GOLD_DIM  = 'rgba(var(--gold-rgb), 0.14)'

// ── Per-streaming-source label/colour — used by the agent activity strip and
// the subagent output cards. Keyed by the `source` field the backend labels
// messages with ("inventory_agent", "sales_agent", ..., "main agent").
const SOURCE_COLORS = {
  inventory: '#22c55e',
  sales:     '#60a5fa',
  marketing: '#f97316',
  finance:   '#facc15',
  research:  '#a855f7',
  supplier:  '#38bdf8',
}

export const SOURCE_META = {
  inventory_agent: { label: 'Inventory', color: SOURCE_COLORS.inventory },
  sales_agent:     { label: 'Sales',     color: SOURCE_COLORS.sales },
  marketing_agent: { label: 'Marketing', color: SOURCE_COLORS.marketing },
  finance_agent:   { label: 'Finance',   color: SOURCE_COLORS.finance },
  research_agent:  { label: 'Research',  color: SOURCE_COLORS.research },
  supplier_agent:  { label: 'Supplier',  color: SOURCE_COLORS.supplier },
  'main agent':    { label: 'Supervisor', color: GOLD },
}

export function sourceMeta(source) {
  if (SOURCE_META[source]) return SOURCE_META[source]
  if (source && source.includes(' > ')) {
    const first = source.split(' > ')[0]
    if (SOURCE_META[first]) return SOURCE_META[first]
    if (SOURCE_COLORS[first]) return { label: first, color: SOURCE_COLORS[first] }
    return { label: first, color: '#94a3b8' }
  }
  if (source && SOURCE_COLORS[source]) return { label: source, color: SOURCE_COLORS[source] }
  return { label: source || 'agent', color: '#94a3b8' }
}

// ── Urgency / level colour helpers ─────────────────────────────────────────────
export const URGENCY_COLOR = {
  critical: '#ef4444',
  high:     '#f97316',
  normal:   GOLD,
  healthy:  '#22c55e',
  warning:  '#f97316',
  info:     '#60a5fa',
}

// ── Icon/colour per underlying pipeline agent — used to render chips when a
// tool result spans multiple agents (e.g. check_agent_analysis_status once
// done → "inventory,trend,pricing"). Replaces the old SUBAGENT_META, which
// was keyed by "-agent" suffixed subagent names that don't exist anymore.
export const AGENT_META = {
  inventory: { label: 'Inventory', Icon: Package,    color: '#22c55e' },
  trend:     { label: 'Trends',    Icon: TrendingUp, color: '#a78bfa' },
  pricing:   { label: 'Pricing',   Icon: Tag,        color: GOLD      },
  marketing: { label: 'Marketing', Icon: Megaphone,  color: '#f97316' },
  content:   { label: 'Content',   Icon: FileText,   color: '#60a5fa' },
  restock:   { label: 'Restock',   Icon: Package,    color: '#38bdf8' },
  returns:   { label: 'Returns',   Icon: Tag,        color: '#f87171' },
  dm:        { label: 'DMs',       Icon: Megaphone,  color: '#e879f9' },
}

// ── Tool call → display label ──────────────────────────────────────────────────
// Single source of truth for ToolCallCard labels. There are no more per-agent
// subagent_start/subagent_done events — everything streams as generic
// tool_call/tool_result now.
export const TOOL_LABELS = {
  get_pipeline_status:   'Pipeline Status',
  get_inventory_status:  'Inventory Status',
  get_critical_skus:     'Critical SKUs',
  get_open_alerts:       'Open Alerts',
  get_pending_approvals: 'Pending Approvals',
  get_sku_history:       'SKU History',
  get_return_insights:   'Return Insights',
  get_content_queue:     'Content Queue',
  get_run_history:       'Run History',
  start_agent_analysis:        'Queue Pipeline Run',
  check_agent_analysis_status: 'Pipeline Status Check',
  read_file:             'Read Memory',
  edit_file:             'Edit Memory',
}

// ── PrettyJSON key label overrides ─────────────────────────────────────────────
export const KEY_LABEL_OVERRIDES = { sku: 'SKU', roas_7d: 'ROAS (7d)', ctr_7d: 'CTR (7d)' }

// ── Empty-state suggested prompts ──────────────────────────────────────────────
export const SUGGESTIONS = [
  "What's the current inventory status?",
  'Run a full daily pipeline',
  'Which SKUs need restocking today?',
  'Show me the latest pricing analysis',
]