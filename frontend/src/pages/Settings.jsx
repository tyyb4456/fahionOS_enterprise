import { useEffect, useState } from 'react'
import { useApi } from '../api/client'
import { useSearchParams } from 'react-router-dom'
import { Check, ExternalLink, Trash2 } from 'lucide-react'

const gradBtn = {
  background: 'transparent',
  color: '#d4d4d8',
  border: '1px solid rgba(212,212,216,0.45)',
}

function ConnectCard({ title, connected, onConnect, onDisconnect, children }) {
  return (
    <div className="page-card space-y-4" style={{ padding: '20px' }}>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h2>
        {connected
          ? <span className="text-xs flex items-center gap-1" style={{ color: '#4ade80' }}><Check size={10} /> Connected</span>
          : <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>Not connected</span>}
      </div>
      {children}
      <div>
        {!connected
          ? <button onClick={onConnect}
              className="flex items-center gap-2 text-xs px-4 py-2 rounded-xl transition-all hover:opacity-85"
              style={gradBtn}>
              <ExternalLink size={12} /> Connect
            </button>
          : <button onClick={onDisconnect}
              className="flex items-center gap-2 text-xs px-4 py-2 rounded-xl transition-all"
              style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.25)' }}>
              <Trash2 size={12} /> Disconnect
            </button>}
      </div>
    </div>
  )
}

function Field({ label, name, value, onChange, placeholder }) {
  const inputBase = {
    width: '100%', background: 'var(--input-bg)',
    border: '1px solid var(--input-border)', borderRadius: '10px',
    padding: '8px 12px', fontSize: '0.875rem', color: 'var(--text-body)', outline: 'none',
  }
  return (
    <div>
      <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{label}</label>
      <input name={name} value={value} onChange={onChange} placeholder={placeholder} style={inputBase}
        onFocus={e => e.target.style.borderColor = '#d4d4d8'}
        onBlur={e => e.target.style.borderColor = 'var(--input-border)'} />
    </div>
  )
}

export default function Settings() {
  const api                         = useApi()
  const [searchParams]              = useSearchParams()
  const [brand, setBrand]           = useState(null)
  const [shopInput, setShopInput]   = useState('')
  const [form, setForm]             = useState({})
  const [saving, setSaving]         = useState(false)
  const [saved, setSaved]           = useState(false)
  const [loading, setLoading]       = useState(true)

  useEffect(() => {
    api.get('/api/v1/brands/me')
      .then(b => { setBrand(b); setForm({ brand_name: b.brand_name, brand_owner_whatsapp: b.brand_owner_whatsapp || '', brand_owner_email: b.brand_owner_email || '' }) })
      .catch(console.error).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (searchParams.get('shopify') === 'connected') setBrand(b => b ? { ...b, shopify_connected: true } : b)
    if (searchParams.get('meta')    === 'connected') setBrand(b => b ? { ...b, meta_connected: true, instagram_connected: true } : b)
  }, [searchParams])

  const connectShopify    = async () => { if (!shopInput.trim()) return alert('Enter shop name first.'); const { url } = await api.get(`/api/v1/oauth/shopify/start?shop=${shopInput.trim()}`); window.location.href = url }
  const connectMeta       = async () => { const { url } = await api.get('/api/v1/oauth/meta/start'); window.location.href = url }
  const disconnectShopify = async () => { if (!confirm('Disconnect Shopify?')) return; await api.del('/api/v1/brands/me/shopify'); setBrand(b => ({ ...b, shopify_connected: false })) }
  const disconnectMeta    = async () => { if (!confirm('Disconnect Meta?')) return;    await api.del('/api/v1/brands/me/meta');    setBrand(b => ({ ...b, meta_connected: false, instagram_connected: false })) }
  const onChange = e => setForm(f => ({ ...f, [e.target.name]: e.target.value }))
  const save = async () => {
    setSaving(true)
    try { const updated = await api.put('/api/v1/brands/me', form); setBrand(updated); setSaved(true); setTimeout(() => setSaved(false), 3000) }
    catch (e) { alert(e.message) } finally { setSaving(false) }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 rounded-full border-2 animate-spin"
        style={{ borderColor: 'rgba(212,212,216,0.22)', borderTopColor: '#d4d4d8' }} />
    </div>
  )

  const inputBase = {
    width: '100%', background: 'var(--input-bg)',
    border: '1px solid var(--input-border)', borderRadius: '10px',
    padding: '8px 12px', fontSize: '0.875rem', color: 'var(--text-body)', outline: 'none',
  }

  return (
    <div className="p-6 max-w-2xl space-y-6" style={{ position: 'relative', zIndex: 1 }}>
      <div>
        <div className="section-pill">⚙ Configuration</div>
        <h1 className="page-title-shimmer text-2xl" style={{ fontFamily: "'Alfa Slab One', serif" }}>Settings</h1>
        {brand && <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{brand.owner_email} · {brand.plan} plan</p>}
        <div className="gradient-accent-line" />
      </div>

      {searchParams.get('shopify') === 'connected' && (
        <div className="rounded-xl px-4 py-3 text-sm"
          style={{ background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.2)', color: '#4ade80' }}>
          ✓ Shopify connected. Webhooks registered automatically.
        </div>
      )}
      {searchParams.get('meta') === 'connected' && (
        <div className="rounded-xl px-4 py-3 text-sm"
          style={{ background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.2)', color: '#4ade80' }}>
          ✓ Meta connected. Ad account and Instagram page detected.
        </div>
      )}

      <div className="page-card space-y-4" style={{ padding: '20px' }}>
        <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Brand Info</h2>
        <Field label="Brand Name"                   name="brand_name"           value={form.brand_name           || ''} onChange={onChange} />
        <Field label="Owner WhatsApp (for alerts)"  name="brand_owner_whatsapp" value={form.brand_owner_whatsapp || ''} onChange={onChange} placeholder="923001234567" />
        <Field label="Owner Email (for digests)"    name="brand_owner_email"    value={form.brand_owner_email    || ''} onChange={onChange} placeholder="you@example.com" />
        <div className="flex items-center gap-3">
          <button onClick={save} disabled={saving}
            className="text-sm px-5 py-2 rounded-xl transition-all hover:opacity-85 disabled:opacity-50"
            style={gradBtn}>
            {saving ? 'Saving...' : 'Save'}
          </button>
          {saved && <span className="text-xs flex items-center gap-1" style={{ color: '#4ade80' }}><Check size={10} /> Saved</span>}
        </div>
      </div>

      <ConnectCard title="Shopify" connected={brand?.shopify_connected}
        onConnect={connectShopify} onDisconnect={disconnectShopify}>
        {!brand?.shopify_connected && (
          <div>
            <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Shop name</label>
            <input value={shopInput} onChange={e => setShopInput(e.target.value)}
              placeholder="mybrand (without .myshopify.com)" style={inputBase}
              onFocus={e => e.target.style.borderColor = '#d4d4d8'}
              onBlur={e => e.target.style.borderColor = 'var(--input-border)'} />
          </div>
        )}
        {brand?.shopify_connected && (
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Products, orders, inventory and webhooks are syncing automatically.
          </p>
        )}
      </ConnectCard>

      <ConnectCard title="Meta (Facebook Ads + Instagram)" connected={brand?.meta_connected}
        onConnect={connectMeta} onDisconnect={disconnectMeta}>
        {brand?.meta_connected ? (
          <div className="space-y-1">
            {brand.meta_ad_account_id && (
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                Ad Account: <span style={{ color: 'var(--text-body)' }}>{brand.meta_ad_account_id}</span>
              </p>
            )}
            {brand.instagram_page_id && (
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                Instagram Page: <span style={{ color: 'var(--text-body)' }}>{brand.instagram_page_id}</span>
              </p>
            )}
          </div>
        ) : (
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Connects Facebook Ads, Instagram DMs, and ad management in one click.
          </p>
        )}
      </ConnectCard>
    </div>
  )
}