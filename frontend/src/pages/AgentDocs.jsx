import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi } from '../api/client'
import {
  Package, TrendingUp, Megaphone, Coins, FlaskConical, Truck, Headphones, Shirt,
  FileUp, FileText, Trash2, Loader2, Check,
} from 'lucide-react'
import { PageHeader } from '../components/ui'

const AGENTS = [
  { id: 'inventory',        label: 'Inventory',        Icon: Package,     color: '#22c55e' },
  { id: 'sales',            label: 'Sales',            Icon: TrendingUp,  color: '#60a5fa' },
  { id: 'marketing',        label: 'Marketing',        Icon: Megaphone,   color: '#f97316' },
  { id: 'finance',          label: 'Finance',          Icon: Coins,       color: '#facc15' },
  { id: 'research',         label: 'Research',         Icon: FlaskConical, color: '#a855f7' },
  { id: 'supplier',         label: 'Supplier',         Icon: Truck,       color: '#38bdf8' },
  { id: 'customer_support', label: 'Customer Support', Icon: Headphones,  color: '#e879f9' },
  { id: 'product',         label: 'Product',          Icon: Shirt,       color: '#f472b6' },
]

const HINTS = {
  inventory: 'Stock policy, reorder thresholds, seasonal demand guidelines',
  sales: 'Sales SOP, pricing strategy, discount rules, revenue goals',
  marketing: 'Brand voice, content calendar, campaign guidelines',
  finance: 'Budget policy, expense approval rules, cashflow priorities',
  research: 'Market focus areas, competitor watchlist, category priors',
  supplier: 'Supplier expectations, quality standards, procurement rules',
  customer_support: 'Return/exchange policy, response SOP, tone guidelines',
  product: 'Product strategy, merchandising guidelines, collection planning rules',
}

const fmtDate = (iso) => {
  if (!iso) return ''
  try { return new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' }) } catch { return iso }
}

export default function AgentDocs() {
  const api = useApi()
  const [searchParams] = useSearchParams()
  const requested = searchParams.get('agent') || 'inventory'
  const [agent, setAgent] = useState(AGENTS.some(a => a.id === requested) ? requested : 'inventory')

  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [msg, setMsg] = useState(null)
  const fileRef = useRef(null)

  useEffect(() => { document.title = 'Agent documents · FashionOS' }, [])

  const load = useCallback(async (id) => {
    setLoading(true)
    try { setDocs(await api.get(`/api/v1/brands/me/policies/${id}`)) }
    catch (e) { setDocs([]); setMsg({ text: `Couldn't load documents: ${e.message}`, ok: false }) }
    finally { setLoading(false) }
  }, [api])

  useEffect(() => {
    const t = setTimeout(() => load(agent), 0)
    return () => clearTimeout(t)
  }, [agent, load])

  const uploadFile = async (file) => {
    if (!file) return
    setUploading(true); setMsg(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await api.upload(`/api/v1/brands/me/policies/${agent}`, fd)
      setMsg({ text: `✓ ${res.filename} — ${res.chunks_indexed} chunks indexed for the ${agent} agent.`, ok: true })
      load(agent)
    } catch (e) { setMsg({ text: e.message, ok: false }) }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = '' }
  }

  const removeDoc = async (id, filename) => {
    if (!confirm(`Delete "${filename}"? Its chunks will be removed from agent memory.`)) return
    try { await api.del(`/api/v1/brands/me/policies/${agent}/${id}`); setDocs(d => d.filter(x => x.id !== id)) }
    catch (e) { setMsg({ text: e.message, ok: false }) }
  }

  const active = AGENTS.find(a => a.id === agent)

  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) uploadFile(file)
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px 64px', position: 'relative', zIndex: 1 }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <PageHeader
        eyebrow="Agent knowledge"
        title="Agent documents"
        sub="Upload policies, SOPs and strategy docs per agent — they&apos;re parsed, chunked and indexed into that agent&apos;s memory."
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

      {msg && (
        <div className="rounded-xl px-4 py-3 text-sm mb-4" style={{
          background: msg.ok ? 'rgba(74,222,128,0.08)' : 'rgba(239,68,68,0.08)',
          border: `1px solid ${msg.ok ? 'rgba(74,222,128,0.2)' : 'rgba(239,68,68,0.2)'}`,
          color: msg.ok ? '#4ade80' : '#f87171',
        }}>
          {msg.text}
        </div>
      )}

      {/* Upload zone */}
      <div
        onClick={() => fileRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        style={{
          border: `1.5px dashed ${dragOver ? 'var(--gold)' : 'var(--card-border)'}`,
          borderRadius: '12px', padding: '34px 20px', textAlign: 'center', cursor: 'pointer',
          background: dragOver ? 'var(--hover-bg)' : 'var(--card-bg)',
          transition: 'border-color 0.15s, background 0.15s', position: 'relative', overflow: 'hidden',
        }}>
        <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.txt,.md" hidden
          onChange={e => e.target.files?.[0] && uploadFile(e.target.files[0])} />
        <div style={{ width: 44, height: 44, borderRadius: '50%', margin: '0 auto 12px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: `${active.color}1a`, border: `1px solid ${active.color}44`, color: active.color }}>
          {uploading ? <Loader2 size={17} style={{ animation: 'spin 1s linear infinite' }} /> : <FileUp size={18} />}
        </div>
        <div style={{ fontSize: '0.85rem', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", letterSpacing: '0.03em', color: 'var(--text-primary)' }}>
          {uploading ? 'Uploading & indexing…' : 'Drop a document here, or click to browse'}
        </div>
        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 5, lineHeight: 1.6 }}>
          PDF, DOCX, TXT or MD · up to 20MB<br />{HINTS[agent]}
        </div>
      </div>

      {/* Docs list */}
      <div className="mt-6">
        <div className="section-pill" style={{ marginBottom: 10 }}>Indexed for {active.label}</div>
        {loading ? (
          <div style={{ padding: '30px 0', display: 'flex', justifyContent: 'center' }}>
            <Loader2 size={18} style={{ animation: 'spin 1s linear infinite', opacity: 0.5, color: 'var(--text-muted)' }} />
          </div>
        ) : docs.length === 0 ? (
          <div style={{
            padding: '28px 16px', color: 'var(--text-muted)', fontSize: '0.75rem',
            textAlign: 'center', lineHeight: 1.6, border: '1px dashed var(--card-border)', borderRadius: '10px',
          }}>
            No documents indexed for the {active.label} agent yet.<br />Upload a policy or SOP above and it becomes retrievable in agent chats.
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map(d => (
              <div key={d.id} className="page-card" style={{ padding: '13px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 34, height: 34, borderRadius: 8, flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: `${active.color}14`, border: `1px solid ${active.color}3a`, color: active.color,
                }}>
                  <FileText size={15} />
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif" }}>
                    {d.filename}
                  </div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>
                    {d.chunk_count} chunks · added {fmtDate(d.created_at)}
                  </div>
                </div>
                <span className="text-xs flex items-center gap-1" style={{ color: '#4ade80', whiteSpace: 'nowrap' }}>
                  <Check size={11} /> Indexed
                </span>
                <button onClick={() => removeDoc(d.id, d.filename)} title="Delete document"
                  style={{
                    background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)', color: '#f87171',
                    borderRadius: 8, padding: 6, cursor: 'pointer', display: 'flex', flexShrink: 0,
                  }}>
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}