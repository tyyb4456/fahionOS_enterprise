import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useApi } from '../api/client'
import { Field } from '../components/ui'
import {
  Store, Camera, Truck, UserRound, Check, Loader2, ArrowRight, ExternalLink, Trash2, Sparkles,
} from 'lucide-react'

const mint = '#4ade80'

export default function Setup() {
  const api                = useApi()
  const navigate           = useNavigate()
  const [searchParams]     = useSearchParams()
  const [brand, setBrand]  = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState(false)
  const [saved, setSaved]     = useState(false)
  const [form, setForm]       = useState({})
  const [shopInput, setShopInput] = useState('')
  const [courier, setCourier] = useState({ provider: 'postex', api_key: '', account_id: '' })
  const [courierSaving, setCourierSaving] = useState(false)
  const [courierMsg, setCourierMsg] = useState(null)

  useEffect(() => { document.title = 'Setup · FashionOS' }, [])

  const refreshBrand = (next) => { setBrand(typeof next === 'function' ? next : (b) => ({ ...b, ...next })) }

  useEffect(() => {
    api.get('/api/v1/brands/me')
      .then(b => {
        // OAuth success redirects carry ?shopify=connected / ?meta=connected —
        // reflect them so the setup progress reflects the just-completed step.
        const merged = { ...b }
        if (searchParams.get('shopify') === 'connected') merged.shopify_connected = true
        if (searchParams.get('meta') === 'connected')    { merged.meta_connected = true; merged.instagram_connected = true }
        setBrand(merged)
        setForm({ brand_name: merged.brand_name, brand_owner_whatsapp: merged.brand_owner_whatsapp || '', brand_owner_email: merged.brand_owner_email || '' })
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const shopifyJustConnected = searchParams.get('shopify') === 'connected'
  const metaJustConnected    = searchParams.get('meta') === 'connected'

  const onChange = (e) => setForm(f => ({ ...f, [e.target.name]: e.target.value }))
  const saveBrand = async () => {
    setSaving(true)
    try {
      const updated = await api.put('/api/v1/brands/me', form)
      setBrand(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) { alert(e.message) } finally { setSaving(false) }
  }

  const connectShopify = async () => {
    const shop = shopInput.trim()
    if (!shop) return alert('Enter your Shopify shop name first.')
    try { const { url } = await api.get(`/api/v1/oauth/shopify/start?shop=${shop}`); window.location.href = url }
    catch (e) { alert(e.message) }
  }
  const connectMeta = async () => {
    try { const { url } = await api.get('/api/v1/oauth/meta/start'); window.location.href = url }
    catch (e) { alert(e.message) }
  }
  const disconnectShopify = async () => { if (!confirm('Disconnect Shopify?')) return; await api.del('/api/v1/brands/me/shopify'); refreshBrand({ shopify_connected: false }) }
  const disconnectMeta    = async () => { if (!confirm('Disconnect Meta?')) return;    await api.del('/api/v1/brands/me/meta');    refreshBrand({ meta_connected: false, instagram_connected: false }) }
  const onCourierField = (e) => setCourier(c => ({ ...c, [e.target.name]: e.target.value }))
  const connectCourier = async () => {
    setCourierSaving(true); setCourierMsg(null)
    try {
      await api.put('/api/v1/brands/me/courier', { provider: courier.provider, api_key: courier.api_key.trim(), account_id: courier.account_id.trim() || undefined })
      setCourierMsg({ ok: true, text: 'Courier connected.' })
    } catch (e) { setCourierMsg({ ok: false, text: e.message }) } finally { setCourierSaving(false) }
  }
  const disconnectCourier = async () => { await api.del('/api/v1/brands/me/courier'); setCourierMsg({ ok: true, text: 'Courier disconnected.' }) }

  if (loading) return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', opacity: 0.5, color: 'var(--text-muted)' }} />
    </div>
  )

  const essentialDone = brand?.brand_name && brand?.shopify_connected

  const steps = [
    { key: 'brand',    label: 'Brand',   Icon: UserRound, done: !!brand?.brand_name },
    { key: 'shopify',  label: 'Shopify', Icon: Store,     done: brand?.shopify_connected },
  ]
  const doneCount = steps.filter(s => s.done).length
  const pct = Math.round((doneCount / steps.length) * 100)

  const btn = {
    display: 'inline-flex', alignItems: 'center', gap: 8,
    padding: '9px 18px', borderRadius: '10px', cursor: 'pointer',
    fontSize: '0.78rem', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif",
    letterSpacing: '0.04em', transition: 'opacity 0.15s', border: '1px solid var(--card-border)',
    background: 'var(--hover-bg)', color: 'var(--text-primary)',
  }
  const moneyTrail = {
    display: 'inline-flex', alignItems: 'center', gap: 8,
    padding: '9px 18px', borderRadius: '10px', cursor: 'pointer',
    fontSize: '0.78rem', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif",
    letterSpacing: '0.04em', transition: 'opacity 0.15s',
    background: 'transparent', border: '1px solid rgba(212,212,216,0.45)', color: '#d4d4d8',
  }

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '32px 24px 64px', position: 'relative', zIndex: 1 }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* Header */}
      <div className="text-center mb-8">
        <div className="section-pill" style={{ display: 'inline-block' }}>
          <Sparkles size={11} style={{ display: 'inline', verticalAlign: '-2px', color: 'var(--gold)' }} />  Welcome · Get your brand connected
        </div>
        <h1 style={{
          fontFamily: "'Kola-Regular', serif", fontSize: '2.2rem', fontWeight: 500,
          color: 'var(--text-primary)', margin: '4px 0 2px', lineHeight: 1.1,
        }}>
          Let&apos;s set up <span style={{ color: 'var(--gold)' }}>FashionOS</span>
        </h1>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', maxWidth: 520, margin: '0 auto', lineHeight: 1.6 }}>
          Connect your store in a couple of minutes — your agents will then have live data to work with.
          Steps 1 and 2 are required to unlock your workspace; 3 and 4 are optional and can be added anytime.
        </p>
      </div>

      {/* Progress */}
      <div className="page-card" style={{ padding: '18px 20px', marginBottom: 24 }}>
        <div className="flex items-center gap-4 flex-wrap">
          {steps.map(({ label, Icon, done }, i) => (
            <div key={label} className="flex items-center gap-4">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: done ? 'rgba(74,222,128,0.12)' : 'var(--hover-bg)',
                  border: `1px solid ${done ? 'rgba(74,222,128,0.4)' : 'var(--card-border)'}`,
                  color: done ? mint : 'var(--text-secondary)',
                }}>
                  {done ? <Check size={14} /> : <Icon size={14} />}
                </div>
                <span style={{ fontSize: '0.72rem', color: done ? 'var(--text-primary)' : 'var(--text-muted)', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif" }}>
                  {label}
                </span>
              </div>
              {i < steps.length - 1 && <div style={{ width: 44, height: 1, background: 'var(--card-border)' }} />}
            </div>
          ))}
        </div>
        <div style={{ marginTop: 14, height: 3, background: 'var(--item-bg)', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: mint, transition: 'width 0.4s ease' }} />
        </div>
      </div>

      {shopifyJustConnected && (
        <div className="rounded-xl px-4 py-3 text-sm mb-4" style={{ background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.2)', color: mint }}>
          ✓ Shopify connected — products, orders, inventory and webhooks are syncing automatically.
        </div>
      )}
      {metaJustConnected && (
        <div className="rounded-xl px-4 py-3 text-sm mb-4" style={{ background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.2)', color: mint }}>
          ✓ Meta connected — ad account and Instagram page detected.
        </div>
      )}

      <div className="space-y-6">
        {/* 1. Brand profile */}
        <ConnectCard
          step="1"
          icon={<UserRound size={15} />}
          title="Brand profile"
          desc="Name and contact details your agents use for alerts, digests and ordering."
          complete={saved}
        >
          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Brand name" name="brand_name" value={form.brand_name} onChange={onChange} />
            <Field label="Owner WhatsApp (for alerts)" name="brand_owner_whatsapp" value={form.brand_owner_whatsapp} onChange={onChange} placeholder="923001234567" />
            <Field label="Owner email (for digests)" name="brand_owner_email" value={form.brand_owner_email} onChange={onChange} placeholder="you@example.com" />
          </div>
          <div className="flex items-center gap-3">
            <button onClick={saveBrand} disabled={saving} style={btn}> {saving ? 'Saving…' : 'Save profile'} </button>
            {saved && <span className="text-xs flex items-center gap-1" style={{ color: mint }}><Check size={10} /> Saved</span>}
          </div>
        </ConnectCard>

        {/* 2. Shopify */}
        <ConnectCard
          step="2"
          icon={<Store size={15} />}
          title="Connect Shopify"
          desc="Authorize your store so orders, products, inventory and webhooks flow into FashionOS."
          complete={brand?.shopify_connected}
        >
          {brand?.shopify_connected ? (
            <div className="flex items-center justify-between flex-wrap gap-3">
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                Store connected. Products, orders, inventory and webhooks are syncing automatically.
              </p>
              <button onClick={disconnectShopify} style={{ ...btn, background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.25)' }}>
                <Trash2 size={13} /> Disconnect
              </button>
            </div>
          ) : (
            <div className="flex items-end gap-3 flex-wrap">
              <div style={{ flex: 1, minWidth: 220 }}>
                <Field label="Shop name" hint="e.g. mybrand (without .myshopify.com)" value={shopInput} onChange={e => setShopInput(e.target.value)} placeholder="mybrand" />
              </div>
              <button onClick={connectShopify} style={{ ...moneyTrail, whiteSpace: 'nowrap' }}><ExternalLink size={13} /> Connect Shopify</button>
            </div>
          )}
        </ConnectCard>

        {/* 3. Meta (optional) */}
        <ConnectCard
          step="3"
          icon={<Camera size={15} />}
          title="Connect Meta"
          desc="Facebook Ads, Instagram DMs and ad management — one click. Optional: your agents still run on Shopify alone, add this later anytime."
          optional
          complete={brand?.meta_connected}
        >
          {brand?.meta_connected ? (
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="space-y-1">
                {brand.meta_ad_account_id && (
                  <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Ad account: <span style={{ color: 'var(--text-body)' }}>{brand.meta_ad_account_id}</span></p>
                )}
                {brand.instagram_page_id ? (
                  <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Instagram page: <span style={{ color: 'var(--text-body)' }}>{brand.instagram_page_id}</span></p>
                ) : (
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>No Instagram Business Account linked yet — Instagram features need one.</p>
                )}
              </div>
              <button onClick={disconnectMeta} style={{ ...btn, background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.25)' }}>
                <Trash2 size={13} /> Disconnect
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3 flex-wrap">
              <p className="text-xs flex-1 min-w-[220px]" style={{ color: 'var(--text-secondary)' }}>
                Connects Facebook Ads, Instagram DMs, and ad management in one click.
              </p>
              <button onClick={connectMeta} style={moneyTrail}><ExternalLink size={13} /> Connect Meta</button>
            </div>
          )}
        </ConnectCard>

        {/* 4. Courier (optional) */}
        <ConnectCard
          step="4"
          icon={<Truck size={15} />}
          title="Delivery courier"
          desc="Optional — lets the Customer Support Agent check live delivery status."
          optional
          complete={brand?.courier_connected}
        >
          {brand?.courier_connected ? (
            <div className="flex items-center justify-between flex-wrap gap-3">
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                Courier connected — the support agent can now check live delivery status.
              </p>
              <button onClick={disconnectCourier} style={{ ...btn, background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.25)' }}>
                <Trash2 size={13} /> Disconnect
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Provider</label>
                <select name="provider" value={courier.provider} onChange={onCourierField}
                  style={{ width: '100%', background: 'var(--input-bg)', border: '1px solid var(--input-border)', borderRadius: '10px', padding: '9px 12px', fontSize: '0.875rem', color: 'var(--text-body)', outline: 'none' }}>
                  <option value="postex">PostEx (Pakistan)</option>
                  <option value="leopards">Leopards Courier (Pakistan)</option>
                </select>
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <Field label="API key" name="api_key" value={courier.api_key} onChange={onCourierField} placeholder="••••••••" />
                <Field label="Account id (Leopards: api_password)" name="account_id" value={courier.account_id} onChange={onCourierField} placeholder="optional" />
              </div>
              <div className="flex items-center gap-3">
                <button onClick={connectCourier} disabled={courierSaving || !courier.api_key.trim()} style={btn}>
                  {courierSaving ? 'Connecting…' : 'Connect courier'}
                </button>
                {courierMsg && <span className="text-xs" style={{ color: courierMsg.ok ? mint : '#f87171' }}>{courierMsg.text}</span>}
              </div>
            </div>
          )}
        </ConnectCard>
      </div>

      {/* Finish */}
      <div className="page-card mt-6" style={{ padding: '24px 24px', textAlign: 'center', border: essentialDone ? '1px solid rgba(74,222,128,0.35)' : '1px solid var(--card-border)' }}>
        {essentialDone ? (
          <>
            <h2 style={{ fontFamily: "'Kola-Regular', serif", fontSize: '1.3rem', color: 'var(--text-primary)', margin: '0 0 4px' }}>
              You&apos;re ready <span style={{ color: mint }}>✓</span>
            </h2>
            <p className="text-xs mb-5" style={{ color: 'var(--text-secondary)' }}>
              Your brand and store are connected. Add Meta or a courier anytime from this page, then jump into your dashboard.
            </p>
            <button onClick={() => navigate('/dashboard')} style={{ ...moneyTrail, background: `rgba(74,222,128,0.12)`, border: '1px solid rgba(74,222,128,0.4)', color: mint }}>
              Continue to dashboard <ArrowRight size={14} />
            </button>
          </>
        ) : (
          <>
            <h2 style={{ fontFamily: "'Kola-Regular', serif", fontSize: '1.3rem', color: 'var(--text-primary)', margin: '0 0 4px' }}>
              Finish connecting your brand &amp; store
            </h2>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              Complete steps 1 and 2 above to unlock your workspace. Meta and courier can be added later.
            </p>
          </>
        )}
      </div>
    </div>
  )
}

function ConnectCard({ step, icon, title, desc, complete, optional, children, dark }) {
  return (
    <div style={Object.assign({}, {
      position: 'relative', padding: '20px',
      borderRadius: '0', border: '1px solid var(--card-border)',
      background: 'var(--card-bg)', overflow: 'hidden',
      transition: 'border-color 0.25s ease',
    }, complete && dark ? {} : {})}>
      <div style={{ position: 'absolute', top: 0, right: 0, width: '120px', height: '120px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(212,212,216,0.06), transparent)', transform: 'translate(40%, -40%)', pointerEvents: 'none' }} />
      <div className="flex items-center justify-between gap-3 mb-3">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 30, height: 30, borderRadius: 8, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: complete ? 'rgba(74,222,128,0.12)' : 'var(--hover-bg)',
            border: `1px solid ${complete ? 'rgba(74,222,128,0.4)' : 'var(--card-border)'}`,
            color: complete ? mint : 'var(--gold)',
          }}>
            {complete ? <Check size={15} /> : icon}
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: '0.58rem', color: 'var(--text-muted)', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", letterSpacing: '0.1em' }}>STEP {step}</span>
              {optional && <span style={{ fontSize: '0.55rem', color: 'var(--text-muted)', border: '1px solid var(--card-border)', borderRadius: 6, padding: '0 6px', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Optional</span>}
            </div>
            <h3 style={{ fontFamily: "'Kola-Regular', serif", fontSize: '1.02rem', fontWeight: 500, color: 'var(--text-primary)', margin: '1px 0 0', letterSpacing: '0.02em' }}>{title}</h3>
          </div>
        </div>
        {complete && (
          <span className="text-xs flex items-center gap-1" style={{ color: mint, whiteSpace: 'nowrap' }}><Check size={11} /> Connected</span>
        )}
      </div>
      <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)', lineHeight: 1.5, maxWidth: 600 }}>{desc}</p>
      {children}
    </div>
  )
}