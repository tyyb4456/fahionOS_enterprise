import { Package, TrendingUp, Tag, Megaphone, FileText } from 'lucide-react'

export const GOLD     = 'var(--gold)'
export const GOLD_DIM  = 'rgba(var(--gold-rgb), 0.14)'

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