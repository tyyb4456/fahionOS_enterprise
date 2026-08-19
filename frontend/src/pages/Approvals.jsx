import { useEffect, useMemo, useState } from 'react'
import { useApi } from '../api/client'
import { PageHeader } from '../components/ui'
import {
  Check, X, Loader2, ClipboardCheck, ShoppingCart, RotateCcw, RefreshCw,
  FileStack, Truck, CheckCircle2, XCircle, Clock,
} from 'lucide-react'

const KIND_META = {
  reorder:  { label: 'Reorder',  agent: 'Inventory',       icon: ShoppingCart,  color: '#22c55e' },
  refund:   { label: 'Refund',   agent: 'Customer Support', icon: RotateCcw,    color: '#f87171' },
  exchange: { label: 'Exchange', agent: 'Customer Support', icon: RefreshCw,    color: '#fb923c' },
  quote:    { label: 'Quote',    agent: 'Supplier',        icon: FileStack,     color: '#38bdf8' },
  po:       { label: 'Purchase order', agent: 'Supplier',  icon: Truck,         color: '#a78bfa' },
}

const moneyFmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const fmtMoney = v => (v == null ? '' : moneyFmt.format(v))

function relTime(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.max(0, Math.round(diff / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.round(hrs / 24)}d ago`
}

export default function Approvals() {
  const api      = useApi()

  const [data,    setData]    = useState(null)
  const [dataTab, setDataTab] = useState('')
  const [kind,    setKind]    = useState('all')
  const [tab,     setTab]     = useState('pending')
  const [busyId,  setBusyId]  = useState(null)
  const [note,    setNote]    = useState({})
  const [noteOpen,setNoteOpen]= useState(null)
  const [action,  setAction]  = useState(null)   // {kind, id, title}
  const [flash,   setFlash]   = useState(null)

  useEffect(() => { document.title = 'Approvals · FashionOS' }, [])

  const loading = dataTab !== tab

  const load = () => {
    api.get(`/api/v1/approvals${tab === 'decided' ? '?status=decided' : ''}`)
      .then(res => { setData(res); setDataTab(tab) })
      .catch(e => setFlash({ tone: 'error', text: e.message }))
  }

  useEffect(load, [api, tab])

  const pending = useMemo(() => {
    const items = data?.pending || []
    if (kind === 'all') return items
    return items.filter(i => i.kind === kind)
  }, [data, kind])

  const counts = data?.counts || {}
  const total = data?.total_pending || 0

  const meta = (k) => KIND_META[k] || { label: k, agent: '', icon: ClipboardCheck, color: '#d4d4d8' }

  const decide = async (it, decision) => {
    const body = { note: note[it.id] || undefined }
    setBusyId(it.id)
    try {
      await api.post(`/api/v1/approvals/${it.kind}/${it.id}/${decision}`, body)
      setNote(prev => { const c = { ...prev }; delete c[it.id]; return c })
      setNoteOpen(null)
      setAction(null)
      setFlash({ tone: 'ok', text: `${meta(it.kind).label} ${decision}d` })
      load()
    } catch (e) {
      setFlash({ tone: 'error', text: e.message })
      setBusyId(null)
    }
  }

  return (
    <div style={{ maxWidth: 1240, margin: '0 auto', padding: '32px 24px 64px', position: 'relative', zIndex: 1 }}>
      <PageHeader
        eyebrow="Human-in-the-loop"
        title="Approval Center"
        sub="Review what your agents are waiting on before it executes"
        right={(
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '5px 12px', borderRadius: 999,
            background: total > 0 ? 'rgba(250,204,21,0.1)' : 'var(--hover-bg)',
            border: `1px solid ${total > 0 ? 'rgba(250,204,21,0.4)' : 'var(--card-border)'}`,
            color: total > 0 ? '#facc15' : 'var(--text-muted)',
            fontSize: '0.62rem', fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif",
            letterSpacing: '0.05em',
          }}>
            <Clock size={11} /> {total} pending
          </span>
        )}
      />

      {flash && (
        <div style={{
          marginTop: 14, padding: '10px 14px', borderRadius: 8, fontSize: '0.72rem',
          background: flash.tone === 'ok' ? 'rgba(74,222,128,0.08)' : 'rgba(248,113,113,0.08)',
          border: `1px solid ${flash.tone === 'ok' ? 'rgba(74,222,128,0.3)' : 'rgba(248,113,113,0.3)'}`,
          color: flash.tone === 'ok' ? '#4ade80' : '#f87171',
        }}>{flash.text}</div>
      )}

      {/* Tabs: pending / decided */}
      <div className="mt-4 flex items-center gap-2">
        {[
          { key: 'pending', label: `Pending · ${total}` },
          { key: 'decided', label: 'Decisions' },
        ].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            padding: '7px 14px', cursor: 'pointer', borderRadius: 999,
            background: tab === t.key ? 'var(--active-nav)' : 'transparent',
            border: `1px solid ${tab === t.key ? 'rgba(212,212,216,0.4)' : 'var(--card-border)'}`,
            color: tab === t.key ? 'var(--text-primary)' : 'var(--text-muted)',
            fontSize: '0.62rem', letterSpacing: '0.08em', textTransform: 'uppercase',
            fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif",
            transition: 'all 0.18s ease',
          }}>{t.label}</button>
        ))}
      </div>

      {tab === 'pending' && (
        <>
          {/* Kind filter */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {[['all', 'All', total], ...Object.entries(KIND_META).map(([k, m]) => [k, m.label, counts[k] || 0])].map(([k, label, n]) => (
              <button key={k} onClick={() => setKind(k)} style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '5px 12px', cursor: 'pointer', borderRadius: 999,
                background: kind === k ? 'var(--active-nav)' : 'transparent',
                border: `1px solid ${kind === k ? 'rgba(212,212,216,0.4)' : 'var(--card-border)'}`,
                color: kind === k ? 'var(--text-primary)' : 'var(--text-muted)',
                fontSize: '0.6rem', letterSpacing: '0.06em', textTransform: 'uppercase',
                fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif",
                transition: 'all 0.18s ease',
              }}>
                {label}
                <span style={{
                  fontSize: '0.58rem', fontVariantNumeric: 'tabular-nums',
                  color: n > 0 ? '#facc15' : 'var(--text-muted)', opacity: kind === k ? 1 : 0.7,
                }}>{n}</span>
              </button>
            ))}
          </div>

          {loading ? (
            <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', opacity: 0.5, color: 'var(--text-muted)' }} />
            </div>
          ) : pending.length === 0 ? (
            <div className="page-card" style={{ marginTop: 16, padding: '40px 20px', textAlign: 'center' }}>
              <CheckCircle2 size={22} style={{ color: '#4ade80', opacity: 0.6, margin: '0 auto 10px' }} />
              <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', letterSpacing: '0.05em' }}>
                Nothing awaiting approval — agents have cleared the queue.
              </div>
            </div>
          ) : (
            <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {pending.map(it => {
                const m = meta(it.kind)
                const Icon = m.icon
                return (
                  <div key={`${it.kind}-${it.id}`} className="page-card" style={{
                    padding: '16px 18px',
                    borderLeft: `2px solid ${m.color}${busyId === it.id ? '' : '88'}`,
                    opacity: busyId === it.id ? 0.55 : 1,
                    transition: 'opacity 0.2s ease',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                      <div style={{
                        width: 38, height: 38, borderRadius: '50%', flexShrink: 0,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        background: `${m.color}14`, border: `1px solid ${m.color}44`, color: m.color,
                      }}>
                        <Icon size={16} />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <span style={{ fontSize: '0.78rem', color: 'var(--text-primary)', fontWeight: 600 }}>{it.title}</span>
                          {it.urgency && <span style={{
                            fontSize: '0.55rem', textTransform: 'uppercase', letterSpacing: '0.08em',
                            color: it.urgency === 'critical' ? '#f87171' : it.urgency === 'high' ? '#fb923c' : '#4ade80',
                            border: `1px solid ${it.urgency === 'critical' ? 'rgba(248,113,113,0.4)' : it.urgency === 'high' ? 'rgba(251,146,60,0.4)' : 'rgba(74,222,128,0.35)'}`,
                            padding: '2px 8px', borderRadius: 999,
                          }}>{it.urgency}</span>}
                        </div>
                        <div style={{ fontSize: '0.66rem', color: 'var(--text-secondary)', marginTop: 4, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                          <span>{m.label} · from {m.agent} agent</span>
                          <span>· {relTime(it.created_at)}</span>
                          {it.amount != null && <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{fmtMoney(it.amount)}</span>}
                        </div>
                        {it.summary && (
                          <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', marginTop: 6, lineHeight: 1.5 }}>{it.summary}</div>
                        )}
                        {Object.keys(it.extra || {}).length > 0 && (
                          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                            {Object.entries(it.extra).filter(([, v]) => v != null && v !== '').map(([k, v]) => (
                              <span key={k} style={{
                                fontSize: '0.56rem', padding: '2px 8px', borderRadius: 999,
                                background: 'var(--item-bg)', border: '1px solid var(--item-border)',
                                color: 'var(--text-muted)', textTransform: 'capitalize',
                              }}>{k.replace(/_/g, ' ')}: <span style={{ color: 'var(--text-secondary)' }}>{v}</span></span>
                            ))}
                          </div>
                        )}

                        {/* optional note + actions */}
                        {noteOpen === it.id && (
                          <textarea
                            value={note[it.id] || ''}
                            onChange={e => setNote(prev => ({ ...prev, [it.id]: e.target.value }))}
                            placeholder="Optional note for this decision…"
                            rows={2}
                            style={{
                              width: '100%', marginTop: 10, padding: '8px 10px',
                              background: 'var(--input-bg)', border: '1px solid var(--input-border)',
                              color: 'var(--text-primary)', fontSize: '0.7rem', borderRadius: 6,
                              outline: 'none', resize: 'vertical',
                            }}
                          />
                        )}

                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                          <button
                            disabled={busyId === it.id}
                            onClick={() => action && action.id === it.id ? decide(it, 'approve') : setAction({ kind: it.kind, id: it.id, title: it.title })}
                            style={{
                              display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                              padding: '6px 14px', borderRadius: 6, fontSize: '0.62rem', letterSpacing: '0.05em',
                              background: 'rgba(74,222,128,0.1)', border: '1px solid rgba(74,222,128,0.4)',
                              color: '#4ade80', fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif",
                              transition: 'all 0.18s ease',
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = 'rgba(74,222,128,0.18)'}
                            onMouseLeave={e => e.currentTarget.style.background = 'rgba(74,222,128,0.1)'}
                          >
                            {busyId === it.id ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Check size={11} />}
                            Approve
                          </button>
                          <button
                            disabled={busyId === it.id}
                            onClick={() => action && action.id === it.id ? decide(it, 'reject') : setAction({ kind: it.kind, id: it.id, title: it.title })}
                            style={{
                              display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                              padding: '6px 14px', borderRadius: 6, fontSize: '0.62rem', letterSpacing: '0.05em',
                              background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.35)',
                              color: '#f87171', fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif",
                              transition: 'all 0.18s ease',
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = 'rgba(248,113,113,0.16)'}
                            onMouseLeave={e => e.currentTarget.style.background = 'rgba(248,113,113,0.08)'}
                          >
                            <X size={11} />
                            Reject
                          </button>
                          <button onClick={() => { setNoteOpen(noteOpen === it.id ? null : it.id); setAction(null) }}
                            style={{
                              cursor: 'pointer', background: 'none', border: 'none',
                              color: 'var(--text-muted)', fontSize: '0.6rem', letterSpacing: '0.05em',
                              fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif",
                              padding: '6px 8px',
                            }}>
                            {noteOpen === it.id ? 'Hide note' : 'Add note'}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {tab === 'decided' && (
        <div className="page-card" style={{ marginTop: 16, padding: '16px 18px' }}>
          <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', marginBottom: 10 }}>
            Decisions made by you or the agents — audit trail.
          </div>
          {(data?.decided || []).length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', letterSpacing: '0.05em', padding: '18px 0', textAlign: 'center' }}>
              No decisions logged yet.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(data?.decided || []).map((d, i) => {
                const m = meta(d.kind)
                const ex = d.execution
                const exChip = ex ? (
                  ex.status === 'done'   ? { label: 'Executed', color: '#4ade80', border: 'rgba(74,222,128,0.35)' }
                  : ex.status === 'failed' ? { label: 'Failed · will retry', color: '#f87171', border: 'rgba(248,113,113,0.35)' }
                  : { label: 'Executing…', color: '#facc15', border: 'rgba(250,204,21,0.4)' }
                ) : { label: 'Queued…', color: '#a8a29e', border: 'var(--card-border)' }
                let exDetail
                try { exDetail = ex?.detail ? JSON.parse(ex.detail) : '' } catch { exDetail = ex?.detail || '' }
                return (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px',
                    background: 'var(--item-bg)', border: '1px solid var(--item-border)',
                  }}>
                    {d.decision === 'approve'
                      ? <CheckCircle2 size={13} style={{ color: '#4ade80', flexShrink: 0 }} />
                      : <XCircle size={13} style={{ color: '#f87171', flexShrink: 0 }} />}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '0.68rem', color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {d.title}
                      </div>
                      <div style={{ fontSize: '0.58rem', color: 'var(--text-muted)', marginTop: 2, textTransform: 'capitalize', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {m.label} · {d.decision}d{d.note ? ` · “${d.note}”` : ''} · {relTime(d.decided_at)}
                      </div>
                      {d.decision === 'approve' && exDetail && typeof exDetail === 'object' && exDetail.purchase_order_id && (
                        <div style={{ fontSize: '0.56rem', color: 'var(--text-muted)', marginTop: 2, fontVariantNumeric: 'tabular-nums' }}>
                          PO {exDetail.purchase_order_id.slice(0, 8)}…
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                      {d.decision === 'approve' && (
                        <span style={{
                          fontSize: '0.55rem', textTransform: 'uppercase', letterSpacing: '0.08em',
                          color: exChip.color, border: `1px solid ${exChip.border}`, padding: '2px 8px', borderRadius: 999,
                        }}>{exChip.label}</span>
                      )}
                      <span style={{
                        fontSize: '0.55rem', textTransform: 'uppercase', letterSpacing: '0.08em',
                        color: d.decision === 'approve' ? '#4ade80' : '#f87171',
                        border: `1px solid ${d.decision === 'approve' ? 'rgba(74,222,128,0.35)' : 'rgba(248,113,113,0.35)'}`,
                        padding: '2px 8px', borderRadius: 999,
                      }}>{d.decision === 'approve' ? 'Approved' : 'Rejected'}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
