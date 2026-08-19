import { useEffect, useMemo, useState } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import { useApi } from '../api/client'
import { useUser } from '@clerk/clerk-react'
import {
  MessageSquare, Building2, FilePlus2, Store, Camera, ArrowRight, Loader2,
  Banknote, ShoppingBag, Users, Package, Coins, AlertTriangle, Headphones, Zap,
  SwatchBook, TrendingUp, RotateCcw, Activity as ActivityIcon,
} from 'lucide-react'
import {
  ResponsiveContainer, ComposedChart, Line, Area, BarChart, Bar, Cell,
  PieChart, Pie, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import { PageHeader } from '../components/ui'
import StatCard from '../components/StatCard'

const AGENT_META = {
  inventory:       { label: 'Inventory',  color: '#22c55e' },
  sales:           { label: 'Sales',      color: '#60a5fa' },
  marketing:       { label: 'Marketing',  color: '#f97316' },
  finance:         { label: 'Finance',    color: '#facc15' },
  research:        { label: 'Research',   color: '#a855f7' },
  supplier:        { label: 'Supplier',   color: '#38bdf8' },
  customer_support:{ label: 'Support',    color: '#e879f9' },
  product:        { label: 'Product',    color: '#f472b6' },
}

const STATS = [
  { key: 'revenue_30d',   label: 'Revenue',      unit: 'money',  icon: Banknote,     color: 'green', deltaKey: 'revenue' },
  { key: 'orders_30d',    label: 'Orders',       unit: 'num',    icon: ShoppingBag,  color: 'blue',  deltaKey: 'orders' },
  { key: 'aov',           label: 'Avg order',    unit: 'money',  icon: TrendingUp,   color: 'gold',  deltaKey: 'aov' },
  { key: 'new_customers', label: 'New customers',unit: 'num',    icon: Users,        color: 'purple', deltaKey: 'customers' },
  { key: 'products',      label: 'Products',     unit: 'num',    icon: Package,      color: 'teal', subKey: 'low_stock', subFmt: v => `${v} low stock` },
  { key: 'expenses_30d',  label: 'Expenses',     unit: 'money',  icon: Coins,        color: 'red',   deltaKey: 'expenses', deltaInvert: true },
  { key: 'refunds_count', label: 'Refunds',      unit: 'num',    icon: RotateCcw,    color: 'yellow', deltaKey: 'refunds', deltaInvert: true },
  { key: 'alerts_open',   label: 'Open alerts',  unit: 'num',    icon: AlertTriangle,color: 'yellow' },
  { key: 'tickets_open',  label: 'Open tickets', unit: 'num',    icon: Headphones,   color: 'gold' },
  { key: 'runs',          label: 'Agent runs',   unit: 'num',    icon: Zap,          color: 'teal' },
]

const PIE_SETS = {
  alerts:   { title: 'Inventory alerts · severity', get: d => d.pie.alerts,   fmt: v => v,          color: name => ({ critical: '#f87171', high: '#fb923c', medium: '#facc15', low: '#4ade80' }[name] || '#d4d4d8') },
  tickets:  { title: 'Support tickets · status',    get: d => d.pie.tickets,  fmt: v => v,          color: name => ({ open: '#fb923c', in_progress: '#60a5fa', escalated: '#f87171', resolved: '#4ade80', closed: '#a8a29e' }[name] || '#d4d4d8') },
  expenses: { title: 'Expenses · 30d by category',  get: d => d.pie.expenses, fmt: v => fmtMoney(v), color: () => '#d4d4d8' },
  content:  { title: 'Scheduled content · platform',get: d => d.pie.content,  fmt: v => v,          color: () => '#d4d4d8' },
}

const NUM_COLORS = ['#d4d4d8', '#60a5fa', '#a78bfa', '#4ade80', '#facc15', '#fb923c', '#e879f9', '#38bdf8', '#f87171']

const moneyFmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const moneyCompact = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 })
const numFmt = new Intl.NumberFormat('en-US')
const numCompact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })

function fmtMoney(v) { return moneyFmt.format(v || 0) }
function fmtNum(v)   { return numFmt.format(v || 0) }
function fmtMoneyC(v){ return moneyCompact.format(v || 0) }
function fmtNumC(v)  { return numCompact.format(v || 0) }

const tooltipStyle = {
  background: '#1e1e1e', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8,
  color: 'var(--text-primary)', fontSize: '0.7rem', fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif",
  boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
}

function shortDate(iso) { return iso?.slice(5) || '' }
function fullDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function Dashboard() {
  const api      = useApi()
  const navigate = useNavigate()
  const { user } = useUser()

  const [brand,   setBrand]   = useState(null)
  const [dash,    setDash]    = useState(null)
  const [live,    setLive]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [pieKey,  setPieKey]  = useState('alerts')
  const [days,    setDays]    = useState(30)

  useEffect(() => { document.title = 'Dashboard · FashionOS' }, [])

  useEffect(() => {
    api.get('/api/v1/brands/me')
      .then(setBrand)
      .catch(console.error)
      .finally(() => setLoading(false))

    api.get('/api/v1/office/state').then(setLive).catch(() => {})
  }, [api])

  useEffect(() => {
    api.get(`/api/v1/dashboard?days=${days}`).then(setDash).catch(console.error)
  }, [api, days])

  const lineData = useMemo(() => {
    if (!dash) return []
    const map = new Map()
    for (const r of dash.revenue_series || []) map.set(r.date, { date: r.date, revenue: r.revenue, orders: r.orders, forecast: null })
    for (const f of dash.forecast_series || []) {
      const cur = map.get(f.date)
      map.set(f.date, { date: f.date, revenue: cur ? cur.revenue : null, orders: cur ? cur.orders : 0, forecast: f.revenue })
    }
    return [...map.values()].sort((a, b) => a.date.localeCompare(b.date))
  }, [dash])

  const ready = brand?.brand_name && brand?.shopify_connected
  if (!loading && !ready) return <Navigate to="/setup" replace />

  const numbers = dash?.numbers || {}
  const pieSet  = PIE_SETS[pieKey]
  const pieData = (pieSet ? pieSet.get(dash || { pie: {} }) : undefined) || []
  const pieTotal = pieData.reduce((s, d) => s + (d.value || 0), 0)

  const agents = (dash?.agents || []).map(a => ({
    ...a,
    label: AGENT_META[a.id]?.label || a.label,
    color: AGENT_META[a.id]?.color || '#d4d4d8',
  }))

  if (loading) return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', opacity: 0.5, color: 'var(--text-muted)' }} />
    </div>
  )

  const firstName = user?.firstName || (brand?.brand_name?.split(' ')[0] || 'there')

  const actions = [
    { label: 'Go to chat',    desc: 'Talk to your agents about anything',  Icon: MessageSquare, to: '/chat' },
    { label: 'Go to office',  desc: 'Watch the agents work in real time',  Icon: Building2,    to: '/office' },
    { label: 'Add documents', desc: 'Give each agent your policies & SOPs',Icon: FilePlus2,    to: '/docs' },
  ]

  return (
    <div style={{ maxWidth: 1240, margin: '0 auto', padding: '32px 24px 64px', position: 'relative', zIndex: 1 }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } } @keyframes pulse-dot { 0%,100%{opacity:.35;transform:scale(1)} 50%{opacity:1;transform:scale(1.35)} }`}</style>

      <PageHeader
        eyebrow="Command center"
        title={`Welcome, ${firstName}`}
        sub={`${brand.brand_name} · ${brand.plan} plan · all agents reported`}
        right={(
          <div className="flex items-center gap-2">
            <RangePill current={days} onChange={setDays} />
            <ConnPill ok={brand.shopify_connected} text="Shopify"><Store size={11} /></ConnPill>
            <ConnPill ok={brand.meta_connected} text="Meta"><Camera size={11} /></ConnPill>
          </div>
        )}
      />

      {/* Primary actions */}
      <div className="grid sm:grid-cols-3 gap-4 mt-2">
        {actions.map(({ label, desc, Icon, to }) => (
          <button key={to} onClick={() => navigate(to)} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14,
            padding: '18px 20px', borderRadius: '0', cursor: 'pointer',
            border: '1px solid var(--card-border)', background: 'var(--card-bg)',
            color: 'var(--text-primary)', textAlign: 'left', width: '100%',
            fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif",
            transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
            animation: 'fadeUp .5s ease both',
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--gold)'; e.currentTarget.style.boxShadow = '0 8px 28px rgba(0,0,0,0.25)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--card-border)'; e.currentTarget.style.boxShadow = 'none' }}>
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

      {/* Live agent strip */}
      <div className="page-card" style={{ marginTop: 20, padding: '14px 18px', display: 'flex', flexWrap: 'wrap', gap: '10px 18px', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.62rem', letterSpacing: '0.22em', textTransform: 'uppercase', fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif" }}>
          <ActivityIcon size={13} style={{ color: 'var(--gold)' }} /> Live
        </div>
        {Object.keys(AGENT_META).map(id => {
          const m   = AGENT_META[id]
          const st  = live?.agents?.[id]?.status ?? live?.agents?.[`${id}_agent`]?.status
          const busy = !!st && st !== 'idle'
          return (
            <span key={id} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: '0.66rem', color: 'var(--text-secondary)', letterSpacing: '0.03em' }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: busy ? m.color : '#3f3f46', boxShadow: busy ? `0 0 8px ${m.color}` : 'none', animation: busy ? 'pulse-dot 1.6s ease-in-out infinite' : 'none' }} />
              {m.label}
            </span>
          )
        })}
      </div>

      {/* KPI numbers */}
      <div className="mt-5 grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3">
        {STATS.map(s => {
          const v = numbers[s.key]
          const sub = s.subKey && numbers[s.subKey] !== undefined
            ? s.subFmt(numbers[s.subKey])
            : undefined
          return (
            <StatCard
              key={s.key}
              label={s.label}
              value={s.unit === 'money' ? fmtMoney(v) : fmtNum(v)}
              sub={sub}
              color={s.color}
              icon={s.icon}
              delta={s.deltaKey ? dash?.deltas?.[s.deltaKey] : undefined}
              deltaInvert={s.deltaInvert}
            />
          )
        })}
      </div>

      {/* Row: line + pie */}
      <div className="mt-4 grid lg:grid-cols-3 gap-4">
        <Panel title="Revenue — actual vs forecast" icon={<TrendingUp size={14} />} className="lg:col-span-2" sub="Last 30 days of orders, plus the agent's forward forecast">
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={lineData} margin={{ top: 10, right: 8, left: 4, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(212,212,216,0.07)" vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} stroke="#78716c" tick={{ fontSize: 10, fill: '#78716c' }} tickLine={false} axisLine={{ stroke: 'rgba(120,113,108,0.3)' }} minTickGap={26} />
                <YAxis yAxisId="rev" stroke="#78716c" tick={{ fontSize: 10, fill: '#78716c' }} tickFormatter={fmtMoneyC} tickLine={false} axisLine={false} width={52} />
                <YAxis yAxisId="ord" orientation="right" stroke="#78716c" tick={{ fontSize: 10, fill: '#78716c' }} tickFormatter={fmtNumC} tickLine={false} axisLine={false} width={38} />
                <Tooltip
                  contentStyle={tooltipStyle} labelFormatter={fullDate}
                  formatter={(v, n) => [n === 'forecast' ? fmtMoney(v) : (n === 'orders' ? fmtNum(v) : fmtMoney(v)), n === 'forecast' ? 'Forecast' : n === 'orders' ? 'Orders' : 'Revenue']}
                />
                <Bar yAxisId="ord" dataKey="orders" name="orders" fill="#60a5fa" fillOpacity={0.28} maxBarSize={12} radius={[2, 2, 0, 0]} />
                <Area yAxisId="rev" dataKey="revenue" name="revenue" type="monotone" stroke="#d4d4d8" strokeWidth={2} fill="url(#revGrad)" fillOpacity={0.35} dot={false} activeDot={{ r: 4, fill: '#d4d4d8' }} connectNulls={false} />
                <defs>
                  <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#d4d4d8" stopOpacity={0.32} />
                    <stop offset="100%" stopColor="#d4d4d8" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <Line yAxisId="rev" dataKey="forecast" name="forecast" type="monotone" stroke="#a855f7" strokeWidth={2} strokeDasharray="6 4" dot={false} connectNulls={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginTop: 8, fontSize: '0.64rem', color: 'var(--text-secondary)', letterSpacing: '0.04em' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 14, height: 2, background: '#d4d4d8' }} /> Actual revenue</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 8, background: 'rgba(96,165,250,0.5)' }} /> Orders</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 14, height: 0, borderTop: '2px dashed #a855f7' }} /> Forecast</span>
          </div>
        </Panel>

        <Panel title={pieSet.title} icon={<SwatchBook size={14} />} sub="Breakdown across the agent estate">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
            {Object.keys(PIE_SETS).map(k => (
              <button key={k} onClick={() => setPieKey(k)} style={{
                padding: '5px 10px', cursor: 'pointer', borderRadius: 999,
                background: k === pieKey ? 'var(--active-nav)' : 'transparent',
                border: `1px solid ${k === pieKey ? 'rgba(212,212,216,0.4)' : 'var(--card-border)'}`,
                color: k === pieKey ? 'var(--text-primary)' : 'var(--text-muted)',
                fontSize: '0.58rem', letterSpacing: '0.08em', textTransform: 'uppercase',
                fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif",
                transition: 'all 0.18s ease',
              }}>{k}</button>
            ))}
          </div>

          {pieData.length === 0 ? (
            <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '0.7rem', letterSpacing: '0.06em' }}>
              No data yet — run some agents
            </div>
          ) : (
            <>
              <div style={{ height: 190, position: 'relative' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name"
                      innerRadius={52} outerRadius={78} paddingAngle={3} strokeWidth={0}
                      cornerRadius={4}>
                      {pieData.map((d, i) => (
                        <Cell key={d.name} fill={pieSet.color(d.name) || NUM_COLORS[i % NUM_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} formatter={(v, n) => [pieSet.fmt(v), n]} />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{
                  position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
                }}>
                  <div style={{ fontFamily: "'Kola-Regular',serif", fontSize: '1.5rem', color: 'var(--text-primary)', lineHeight: 1 }}>{fmtNum(pieTotal)}</div>
                  <div style={{ fontSize: '0.52rem', color: 'var(--text-muted)', letterSpacing: '0.16em', textTransform: 'uppercase', marginTop: 4 }}>total</div>
                </div>
              </div>
              <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {pieData.map(d => (
                  <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.66rem' }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: pieSet.color(d.name) || '#d4d4d8', flexShrink: 0 }} />
                    <span style={{ color: 'var(--text-secondary)', flex: 1, textTransform: 'capitalize' }}>{d.name.replace(/_/g, ' ')}</span>
                    <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{pieSet.fmt(d.value)}</span>
                    <span style={{ color: 'var(--text-muted)', width: 36, textAlign: 'right' }}>{pieTotal ? Math.round((d.value / pieTotal) * 100) : 0}%</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Panel>
      </div>

      {/* Row: bar + activity */}
      <div className="mt-4 grid lg:grid-cols-3 gap-4">
        <Panel title="What your agents have produced" icon={<ActivityIcon size={14} />} className="lg:col-span-2" sub="Records written across every agent estate">
          <div style={{ height: 280 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={agents} margin={{ top: 10, right: 8, left: 4, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(212,212,216,0.07)" vertical={false} />
                <XAxis dataKey="label" stroke="#78716c" tick={{ fontSize: 10, fill: '#78716c' }} tickLine={false} axisLine={{ stroke: 'rgba(120,113,108,0.3)' }} />
                <YAxis stroke="#78716c" tick={{ fontSize: 10, fill: '#78716c' }} tickFormatter={fmtNumC} tickLine={false} axisLine={false} width={40} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(212,212,216,0.06)' }}
                  formatter={(v) => [fmtNum(v), 'Records']} labelFormatter={(l) => `${l} agent`} />
                <Bar dataKey="count" name="records" radius={[4, 4, 0, 0]} maxBarSize={44}>
                  {agents.map(a => <Cell key={a.id} fill={a.color} fillOpacity={0.9} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 14px', marginTop: 10 }}>
            {agents.map(a => (
              <span key={a.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.6rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: a.color }} /> {a.label}
                <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{fmtNum(a.count)}</span>
              </span>
            ))}
          </div>
        </Panel>

        <Panel title="Latest agent runs" icon={<Zap size={14} />} sub="Recent execution log">
          {dash?.activity?.length === 0 && (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', letterSpacing: '0.05em', padding: '18px 0', textAlign: 'center' }}>
              No runs logged yet — say hi to your agents in chat
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 2, maxHeight: 280, overflowY: 'auto', paddingRight: 4 }}>
            {(dash?.activity || []).map((r, i) => {
              const m    = AGENT_META[r.agent?.replace('_agent', '')] || AGENT_META[r.agent] || { label: r.agent || 'agent', color: '#d4d4d8' }
              const ok   = r.status === 'completed'
              const fail = r.status === 'failed'
              return (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px',
                  background: 'var(--item-bg)', border: '1px solid var(--item-border)',
                }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: fail ? '#f87171' : m.color, boxShadow: ok ? `0 0 8px ${m.color}88` : 'none', flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-primary)', display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.label}</span>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.58rem', whiteSpace: 'nowrap' }}>{relTime(r.created_at)}</span>
                    </div>
                    <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: 2, textTransform: 'capitalize', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {r.task.replace(/_/g, ' ')} · {dur(r.duration_ms)}
                      {r.tools?.length ? ` · ${r.tools.length} tool${r.tools.length === 1 ? '' : 's'}` : ''}
                    </div>
                  </div>
                  <span style={{
                    flexShrink: 0, fontSize: '0.55rem', textTransform: 'uppercase', letterSpacing: '0.08em',
                    color: fail ? '#f87171' : ok ? '#4ade80' : '#facc15',
                    border: `1px solid ${fail ? 'rgba(248,113,113,0.4)' : ok ? 'rgba(74,222,128,0.35)' : 'rgba(250,204,21,0.35)'}`,
                    padding: '2px 8px', borderRadius: 999,
                  }}>{r.status}</span>
                </div>
              )
            })}
          </div>
        </Panel>
      </div>

      {/* Row: top products + refunds */}
      <div className="mt-4 grid lg:grid-cols-3 gap-4">
        <Panel title="Top products" icon={<Package size={14} />} className="lg:col-span-2" sub={`Revenue by product · last ${days}d`}>
          {(dash?.top_products || []).length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', letterSpacing: '0.05em', padding: '18px 0', textAlign: 'center' }}>
              No orders yet — revenue will appear here once Shopify orders sync in
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {dash.top_products.map((p, i) => {
                const pct = dash.top_products[0]?.revenue ? (p.revenue / dash.top_products[0].revenue) * 100 : 0
                return (
                  <div key={p.sku || i} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ width: 22, fontSize: '0.62rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>{i + 1}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginBottom: 4 }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {p.name || p.sku}
                        </span>
                        <span style={{ fontSize: '0.64rem', color: 'var(--text-secondary)', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
                          {fmtNum(p.units)} units · <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{fmtMoney(p.revenue)}</span>
                        </span>
                      </div>
                      <div style={{ height: 6, background: 'var(--item-bg)', border: '1px solid var(--item-border)' }}>
                        <div style={{ height: '100%', width: `${Math.max(pct, 3)}%`, background: '#d4d4d8', opacity: 0.85 }} />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Panel>

        <Panel title="Recent refunds" icon={<RotateCcw size={14} />} sub="Latest returns recorded">
          {(dash?.recent_refunds || []).length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', letterSpacing: '0.05em', padding: '18px 0', textAlign: 'center' }}>
              No refunds logged yet
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 280, overflowY: 'auto', paddingRight: 4 }}>
              {(dash.recent_refunds || []).map((r, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', background: 'var(--item-bg)', border: '1px solid var(--item-border)' }}>
                  <RotateCcw size={12} style={{ color: '#facc15', flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.66rem', color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {r.product_name || r.sku}
                    </div>
                    <div style={{ fontSize: '0.58rem', color: 'var(--text-muted)', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {r.quantity}x {r.return_reason || 'no reason'} · {r.refunded_at ? relTime(r.refunded_at) : ''}
                    </div>
                  </div>
                  <span style={{ fontSize: '0.64rem', color: '#f87171', fontWeight: 600, fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
                    -{fmtMoney(r.refund_amount)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}

function Panel({ title, sub, icon, className, children }) {
  return (
    <div className={`page-card ${className || ''}`} style={{ padding: '18px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
        <span style={{ color: 'var(--gold)', display: 'inline-flex' }}>{icon}</span>
        <span style={{ fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif", fontSize: '0.68rem', letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-primary)' }}>
          {title}
        </span>
      </div>
      {sub && <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginBottom: 14 }}>{sub}</div>}
      {children}
    </div>
  )
}

function RangePill({ current, onChange }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 2,
      padding: '3px', borderRadius: 999,
      background: 'var(--hover-bg)', border: '1px solid var(--card-border)',
    }}>
      {[7, 30, 90].map(d => (
        <button key={d} onClick={() => onChange(d)} style={{
          padding: '3px 10px', borderRadius: 999, cursor: 'pointer',
          background: d === current ? 'var(--active-nav)' : 'transparent',
          border: d === current ? '1px solid rgba(212,212,216,0.4)' : '1px solid transparent',
          color: d === current ? 'var(--text-primary)' : 'var(--text-muted)',
          fontSize: '0.6rem', fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif",
          letterSpacing: '0.05em', transition: 'all 0.18s ease',
        }}>{d}d</button>
      ))}
    </span>
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
      fontSize: '0.62rem', fontFamily: "'Panchang-Variable','Panchang-Regular',sans-serif", letterSpacing: '0.05em',
    }}>
      {children} {text}
    </span>
  )
}

function dur(ms) {
  if (!ms) return ''
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms / 60000)}m`
}

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