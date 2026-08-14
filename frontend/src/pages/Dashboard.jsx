import { useEffect, useState } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import { useApi } from '../api/client'
import { useUser } from '@clerk/clerk-react'
import {
  MessageSquare, Building2, FilePlus2, Store, Camera, ArrowRight,
  Package, TrendingUp, Megaphone, Coins, FlaskConical, Truck, Headphones, Loader2,
} from 'lucide-react'
import { PageHeader } from '../components/ui'

const AGENT_CARDS = [
  { id: 'inventory', label: 'Inventory',  desc: 'Stock levels, alerts & reorder recommendations', Icon: Package,    color: '#22c55e', path: '/api/v1/agents/inventory/alerts' },
  { id: 'sales',     label: 'Sales',      desc: 'Revenue, reports, forecasts & anomalies',        Icon: TrendingUp, color: '#60a5fa', path: '/api/v1/agents/sales/insights' },
  { id: 'marketing', label: 'Marketing',  desc: 'Campaigns, content plans & performance',          Icon: Megaphone,  color: '#f97316', path: '/api/v1/agents/marketing/campaigns' },
  { id: 'finance',   label: 'Finance',    desc: 'P&L, cashflow, expenses & risk',                 Icon: Coins,      color: '#facc15', path: '/api/v1/agents/finance/reports' },
  { id: 'research',  label: 'Research',   desc: 'Trends, competitors & product opportunities',     Icon: FlaskConical, color: '#a855f7', path: '/api/v1/agents/research/trends' },
  { id: 'supplier',  label: 'Supplier',   desc: 'Purchase orders, quotes & supplier scores',       Icon: Truck,      color: '#38bdf8', path: '/api/v1/agents/supplier/purchase-orders' },
  { id: 'customer_support', label: 'Customer Support', desc: 'Tickets, conversations & feedback', Icon: Headphones, color: '#e879f9', path: '/api/v1/agents/customer-support/tickets' },
]

export default function Dashboard() {
  const api     = useApi()
  const navigate = useNavigate()
  const { user } = useUser()

  const [brand, setBrand]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [counts, setCounts]   = useState({})

  useEffect(() => { document.title = 'Dashboard · FashionOS' }, [])

  useEffect(() => {
    api.get('/api/v1/brands/me')
      .then(b => setBrand(b))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!brand || !brand.shopify_connected) return
    let alive = true
    Promise.allSettled(AGENT_CARDS.map(async ({ id, path }) => {
      const rows = await api.get(path)
      return { id, count: Array.isArray(rows) ? rows.length : 0 }
    })).then(results => {
      if (!alive) return
      const next = {}
      for (const r of results) if (r.status === 'fulfilled') next[r.value.id] = r.value.count
      setCounts(next)
    })
    return () => { alive = false }
  }, [brand])

  const ready = brand?.brand_name && brand?.shopify_connected

  if (!loading && !ready) return <Navigate to="/setup" replace />

  const firstName = user?.firstName || (brand?.brand_name?.split(' ')[0] || 'there')

  const actions = [
    { label: 'Go to chat',    desc: 'Talk to your agents about anything', Icon: MessageSquare, to: '/chat', accent: 'var(--gold)' },
    { label: 'Go to office',  desc: 'Watch the agents work in real time',  Icon: Building2,    to: '/office', accent: 'var(--gold)' },
    { label: 'Add documents', desc: 'Give each agent your policies & SOPs', Icon: FilePlus2,  to: '/docs', accent: 'var(--gold)' },
  ]

  const moneyBtn = {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14,
    padding: '18px 20px', borderRadius: '0', cursor: 'pointer',
    border: '1px solid var(--card-border)', background: 'var(--card-bg)',
    color: 'var(--text-primary)', textAlign: 'left', width: '100%',
    fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif",
    transition: 'border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease',
  }

  if (loading) return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', opacity: 0.5, color: 'var(--text-muted)' }} />
    </div>
  )

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '32px 24px 64px', position: 'relative', zIndex: 1 }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <PageHeader
        eyebrow="Command center"
        title={`Welcome, ${firstName}`}
        sub={`${brand.brand_name} · ${brand.plan} plan · ready to run`}
        right={(
          <div className="flex items-center gap-2">
            <ConnPill ok={brand.shopify_connected} text="Shopify"><Store size={11} /></ConnPill>
            <ConnPill ok={brand.meta_connected} text="Meta"><Camera size={11} /></ConnPill>
          </div>
        )}
      />

      {/* Primary actions */}
      <div className="grid sm:grid-cols-3 gap-4 mt-2">
        {actions.map(({ label, desc, Icon, to }) => (
          <button key={to} onClick={() => navigate(to)}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--gold)'; e.currentTarget.style.boxShadow = '0 8px 28px rgba(0,0,0,0.25)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--card-border)'; e.currentTarget.style.boxShadow = 'none' }}
            style={moneyBtn}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
              <div style={{
                width: 40, height: 40, borderRadius: '50%', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'var(--hover-bg)', border: '1px solid var(--card-border)', color: 'var(--gold)',
              }}>
                <Icon size={17} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: '0.82rem', letterSpacing: '0.04em', color: 'var(--text-primary)' }}>{label}</div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2, lineHeight: 1.4 }}>{desc}</div>
              </div>
            </div>
            <ArrowRight size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          </button>
        ))}
      </div>

      {/* Agent at a glance */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-3">
          <div className="section-pill" style={{ marginBottom: 0 }}>Your agents</div>
          <button onClick={() => navigate('/agents')} style={{
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gold)',
            fontSize: '0.7rem', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", letterSpacing: '0.05em',
            display: 'inline-flex', alignItems: 'center', gap: 5,
          }}>
            Open command center <ArrowRight size={12} />
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {AGENT_CARDS.map(({ id, label, desc, Icon, color }) => (
            <button key={id} onClick={() => navigate(`/agents?agent=${id}`)}
              onMouseEnter={e => { e.currentTarget.style.borderColor = `${color}88` }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--card-border)' }}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 10, padding: '13px 14px',
                background: 'var(--card-bg)', border: '1px solid var(--card-border)',
                cursor: 'pointer', textAlign: 'left', color: 'var(--text-primary)',
                fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", transition: 'border-color 0.18s ease',
              }}>
              <div style={{
                width: 30, height: 30, borderRadius: 8, flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: `${color}1a`, border: `1px solid ${color}44`, color,
              }}>
                <Icon size={14} />
              </div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-primary)', letterSpacing: '0.03em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {label}
                </div>
                <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginTop: 2, lineHeight: 1.35 }}>{desc}</div>
                <div style={{ fontSize: '0.6rem', color, marginTop: 6, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                  {counts[id] !== undefined ? `${counts[id]} record${counts[id] === 1 ? '' : 's'}` : '—'}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function ConnPill({ ok, text, children }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 10px', borderRadius: 999,
      background: ok ? 'rgba(74,222,128,0.1)' : 'var(--hover-bg)',
      border: `1px solid ${ok ? 'rgba(74,222,128,0.35)' : 'var(--card-border)'}`,
      color: ok ? '#4ade80' : 'var(--text-muted)',
      fontSize: '0.62rem', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", letterSpacing: '0.05em',
    }}>
      {children} {text}
    </span>
  )
}