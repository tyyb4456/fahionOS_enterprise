import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi } from '../../api/client'
import { Loader2, RefreshCw, Play, Check } from 'lucide-react'
import { AGENTS, agentById } from './agentData'
import DataTable from './DataTable'
import { PageHeader } from '../../components/ui'

export default function Agents() {
  const api = useApi()
  const [searchParams] = useSearchParams()
  const requested = searchParams.get('agent')
  const [agent, setAgent] = useState(requested && AGENTS.some(a => a.id === requested) ? requested : 'inventory')

  const [sections, setSections] = useState({})   // label -> rows
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState(null)

  useEffect(() => { document.title = 'Agent command center · FashionOS' }, [])

  const load = useCallback(async (id) => {
    const meta = agentById(id)
    setLoading(true); setError(null); setSections({})
    const results = await Promise.allSettled(
      meta.sections.map(async ({ label, path }) => ({ label, rows: await api.get(path) }))
    )
    const next = {}
    let firstErr = null
    for (const r of results) {
      if (r.status === 'fulfilled') next[r.value.label] = r.value.rows
      else { firstErr = firstErr || r.reason?.message }
    }
    if (firstErr) setError(firstErr)
    setSections(next)
    setLoading(false)
  }, [api])

  useEffect(() => {
    const t = setTimeout(() => load(agent), 0)
    return () => clearTimeout(t)
  }, [agent, load])

  const runAgent = async () => {
    setRunning(true); setRunResult(null)
    try {
      const res = await api.post(`/api/v1/agents/${agent}/run`, agentById(agent).runBody)
      const text = typeof res === 'string' ? res : (res?.response || Object.keys(res).length ? JSON.stringify(res, null, 2) : 'Done.')
      setRunResult({ ok: true, text: text.slice(0, 400) })
    } catch (e) {
      setRunResult({ ok: false, text: e.message })
    } finally { setRunning(false) }
  }

  const active = agentById(agent)

  return (
    <div style={{ maxWidth: 1140, margin: '0 auto', padding: '32px 24px 64px', position: 'relative', zIndex: 1 }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <PageHeader
        eyebrow="Agent command center"
        title="Agents"
        sub="Browse everything each agent has learned, reported and decided — or trigger a fresh run."
        right={(
          <div className="flex items-center gap-2">
            <button onClick={() => load(agent)} title="Refresh data"
              style={iconBtn}><RefreshCw size={14} /></button>
            <button onClick={runAgent} disabled={running} style={{
              ...moneyBtn, display: 'inline-flex', alignItems: 'center', gap: 7,
              border: `1px solid ${active.color}66`, color: active.color,
              minWidth: 0,
            }}>
              {running
                ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                : <Play size={13} />}
              {running ? 'Running…' : 'Run agent'}
            </button>
          </div>
        )}
      />

      {/* Agent tabs */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0 20px' }}>
        {AGENTS.map(({ id, label, Icon, color }) => (
          <button key={id} onClick={() => setAgent(id)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              padding: '7px 13px', borderRadius: 999, cursor: 'pointer',
              background: agent === id ? `${color}1a` : 'var(--card-bg)',
              border: `1px solid ${agent === id ? `${color}66` : 'var(--card-border)'}`,
              color: agent === id ? color : 'var(--text-secondary)',
              fontSize: '0.7rem', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif",
              letterSpacing: '0.03em', transition: 'all 0.15s',
            }}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      {runResult && (
        <div className="rounded-xl px-4 py-3 text-xs mb-4" style={{
          background: runResult.ok ? 'rgba(74,222,128,0.08)' : 'rgba(239,68,68,0.08)',
          border: `1px solid ${runResult.ok ? 'rgba(74,222,128,0.2)' : 'rgba(239,68,68,0.2)'}`,
          color: runResult.ok ? '#4ade80' : '#f87171', whiteSpace: 'pre-wrap', fontFamily: 'monospace', lineHeight: 1.5,
        }}>
          {runResult.ok && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Check size={12} /> Run finished — </span>}
          {runResult.text}
        </div>
      )}

      {error && (
        <div className="rounded-xl px-4 py-3 text-xs mb-4" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#f87171' }}>
          Some feeds couldn&apos;t load: {error}
        </div>
      )}

      {/* Sections */}
      {loading ? (
        <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', opacity: 0.5, color: 'var(--text-muted)' }} />
        </div>
      ) : (
        <div className="space-y-6">
          {active.sections.map(s => {
            const rows = sections[s.label] || []
            return (
              <div key={s.label} className="page-card" style={{ padding: '18px 20px' }}>
                <div className="flex items-center justify-between mb-3">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: active.color }} />
                    <h3 style={{ fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: '0.74rem', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-primary)', margin: 0 }}>
                      {s.label}
                    </h3>
                  </div>
                  <span style={{ fontSize: '0.62rem', color: 'var(--text-muted)' }}>{Array.isArray(rows) ? rows.length : 0}</span>
                </div>
                {Array.isArray(rows) && rows.length > 0 ? (
                  <DataTable rows={rows} color={active.color} />
                ) : (
                  <div style={{
                    padding: '22px 16px', color: 'var(--text-muted)', fontSize: '0.72rem',
                    textAlign: 'center', lineHeight: 1.6, border: '1px dashed var(--card-border)', borderRadius: '10px',
                  }}>
                    Nothing here yet. Run the {active.label} agent to generate this data.
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

const iconBtn = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  width: 34, height: 34, borderRadius: 8, flexShrink: 0,
  background: 'var(--hover-bg)', border: '1px solid var(--card-border)',
  color: 'var(--text-secondary)', cursor: 'pointer',
}
const moneyBtn = {
  padding: '8px 14px', borderRadius: '10px', cursor: 'pointer', flexShrink: 0,
  fontSize: '0.72rem', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif",
  letterSpacing: '0.04em', background: 'var(--card-bg)', color: 'var(--text-primary)',
  transition: 'opacity 0.15s',
}