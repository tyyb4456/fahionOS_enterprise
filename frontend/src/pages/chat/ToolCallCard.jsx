import { useState } from 'react'
import { BarChart2, Loader2, CheckCircle2, ChevronUp, ChevronDown } from 'lucide-react'
import { GOLD, TOOL_LABELS, AGENT_META } from './constants'
import PrettyJSON from './PrettyJSON'

// The only two tools left that represent "multiple agents ran" — everything
// else is a single flat DB read. See deep_agents/tools/pipeline_tools.py.
const PIPELINE_TOOLS = new Set(['start_agent_analysis', 'check_agent_analysis_status'])

function pipelineAgents(call) {
  // Historical replay: streaming.py relabels agent_name to a comma list once
  // the run is done, e.g. "inventory,trend,pricing" — no tool name at all.
  if (call.name.includes(',')) return call.name.split(',')

  const d = call.data
  if (!d) return []
  if (Array.isArray(d.expanded_agents)) return d.expanded_agents                    // start_agent_analysis
  if (Array.isArray(d.result?.completed_agents)) return d.result.completed_agents   // check_agent_analysis_status (done)
  return []
}

function pipelineStatus(call) {
  const d = call.data
  return d && typeof d === 'object' ? d.status || null : null   // queued | pending | running | done | failed
}

function AgentChips({ names }) {
  return (
    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', padding: '0 12px 8px' }}>
      {names.map(n => {
        const meta = AGENT_META[n]
        const c = meta?.color || GOLD
        return (
          <span key={n} style={{
            fontFamily: "'Knewave', cursive", fontSize: '0.58rem',
            letterSpacing: '0.06em', textTransform: 'uppercase',
            padding: '2px 7px', color: c, border: `1px solid ${c}44`, background: `${c}14`,
          }}>{meta?.label || n}</span>
        )
      })}
    </div>
  )
}

export default function ToolCallCard({ call }) {
  const [expanded, setExpanded] = useState(false)
  const isPipeline = PIPELINE_TOOLS.has(call.name) || call.name.includes(',')
  const baseName = call.name.split('#')[0]
  const label   = call.name.includes(',') ? 'Pipeline Run' : (TOOL_LABELS[baseName] || call.name)
  const hasData = call.status === 'done'
  const agents  = isPipeline ? pipelineAgents(call) : []
  const pStatus = isPipeline ? pipelineStatus(call) : null

  return (
    <div style={{ background: 'var(--item-bg)', border: '1px solid var(--item-border)', width: '100%' }}>
      <div
        onClick={() => hasData && setExpanded(e => !e)}
        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', cursor: hasData ? 'pointer' : 'default' }}
      >
        <BarChart2 size={11} color="var(--text-muted)" style={{ opacity: 0.8 }} />
        <span style={{ fontFamily: "'Knewave', cursive", fontSize: '0.63rem', letterSpacing: '0.06em', color: 'var(--text-secondary)', flex: 1 }}>
          {call.status === 'running' ? 'Calling ' : 'Called '}
          <span style={{ color: GOLD }}>{label}</span>
          {pStatus && pStatus !== 'done' && <span style={{ color: 'var(--text-muted)', opacity: 0.85 }}> · {pStatus}</span>}
        </span>
        {call.status === 'running'
          ? <Loader2 size={10} color={GOLD} style={{ animation: 'spin 1s linear infinite' }} />
          : <CheckCircle2 size={10} color="#22c55e" />}
        {hasData && (expanded ? <ChevronUp size={11} color="var(--text-muted)" style={{ opacity: 0.8 }} /> : <ChevronDown size={11} color="var(--text-muted)" style={{ opacity: 0.8 }} />)}
      </div>
      {agents.length > 0 && <AgentChips names={agents} />}
      {expanded && hasData && (
        <div style={{ padding: '4px 12px 12px', borderTop: '1px solid var(--item-border)' }}>
          <PrettyJSON value={call.data} />
        </div>
      )}
    </div>
  )
}