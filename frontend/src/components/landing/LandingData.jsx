import {
  Package, TrendingUp, Megaphone, Wallet, Search, Truck, MessageCircle, Shirt,
} from 'lucide-react'
import {
  SiMeta, SiInstagram, SiFacebook, SiWhatsapp,
  SiShopify, SiGoogle, SiTiktok, SiRedis,
} from '@icons-pack/react-simple-icons'

// ── 8 agents, as deployed in the backend, in supervisor delegation order ──────
// `mode`: 'autonomous' — acts on its own with guardrails · 'guarded' — records and
// advises; high-stakes changes are checked with Finance / escalated to the founder.
export const agents = [
  {
    step: '01',
    icon: Package,
    title: 'Inventory',
    badge: 'inventory_agent',
    desc: 'Forecasts SKU demand and days-to-stockout, flags stockout & overstock risk, and computes safety stock and reorder quantities. Places real purchase orders, notifies suppliers, and corrects Shopify stock levels.',
    exec: 'Purchase orders · Supplier alerts · Stock correction',
    color: '#22c55e',
    mode: 'autonomous',
  },
  {
    step: '02',
    icon: TrendingUp,
    title: 'Sales',
    badge: 'sales_agent',
    desc: 'The brand\'s Chief Revenue Officer. Computes KPIs, confirms anomalies statistically, forecasts revenue, ranks products, and segments customers. Root-causes revenue shifts and creates real Shopify discount codes.',
    exec: 'Discount codes · Revenue forecasts · Segmenting',
    color: '#60a5fa',
    mode: 'autonomous',
  },
  {
    step: '03',
    icon: Megaphone,
    title: 'Marketing',
    badge: 'marketing_agent',
    desc: 'The CMO. Plans and launches campaigns, ranks target audiences, picks best posting times, and generates on-brand copy. Publishes Instagram posts and launches Meta Ads — never promoting out-of-stock items.',
    exec: 'Instagram posts · Meta Ads · Content scheduling',
    color: '#f97316',
    mode: 'autonomous',
  },
  {
    step: '04',
    icon: Wallet,
    title: 'Finance',
    badge: 'finance_agent',
    desc: 'The CFO. Computes real profit and margin, forecasts cash, ranks products by actual cost, and checks purchase-order affordability. Logs expenses, issues budget recommendations, and flags financial risk.',
    exec: 'Budget sign-off · Expense ledger · Risk flags',
    color: '#facc15',
    mode: 'guarded',
  },
  {
    step: '05',
    icon: Search,
    title: 'Research',
    badge: 'research_agent',
    desc: 'Head of Market Intelligence. Monitors the outside world — trends, competitors, pricing, public sentiment — via web search and news coverage. Records verified opportunities and never overclaims.',
    exec: 'Trend intel · Competitor scans · Opportunity records',
    color: '#a855f7',
    mode: 'guarded',
  },
  {
    step: '06',
    icon: Truck,
    title: 'Supplier',
    badge: 'supplier_agent',
    desc: 'Procurement & supply chain. Finds and scores suppliers, requests and compares quotes, negotiates terms, places purchase orders, tracks shipments, and updates reliability from real delivery outcomes.',
    exec: 'Quotes · Purchase orders · Shipment tracking',
    color: '#38bdf8',
    mode: 'autonomous',
  },
  {
    step: '07',
    icon: MessageCircle,
    title: 'Customer Support',
    badge: 'customer_support_agent',
    desc: 'AI Customer Success Manager. Resolves real issues on WhatsApp, Instagram DM, email, and webchat — order status, returns, exchanges, refunds, cancellations — under the brand\'s actual policy, escalating past safe limits.',
    exec: 'Refunds · Exchanges · Tickets · 4 channels',
    color: '#34d399',
    mode: 'guarded',
  },
  {
    step: '08',
    icon: Shirt,
    title: 'Product',
    badge: 'product_agent',
    desc: 'Head of Product & Merchandising. Sits between market intelligence and the catalog — checks brand fit, competition, supplier feasibility, and real margin before proposing anything, plans variant mixes, collections, and initial production quantities from live sales data, and tracks each product\'s lifecycle from idea to archive.',
    exec: 'Proposals · Collections · Lifecycle',
    color: '#f472b6',
    mode: 'guarded',
  },
]

// ── Stats ─────────────────────────────────────────────────────────────────────
export const stats = [
  { value: '8',   label: 'Specialized Agents', suffix: '' },
  { value: '24',  label: 'Hour Autonomy',       suffix: '/7' },
  { value: '2',   label: 'Agent Layers',        suffix: '' },
  { value: '4',   label: 'Support Channels',    suffix: '' },
]

// ── Platform integrations (real read + write MCP) ─────────────────────────────
export const integrations = [
  {
    Icon: SiShopify,
    name: 'Shopify',
    badge: 'shopify_mcp',
    color: '#96BF48',
    desc: 'Live store reads and writes. Agents pull catalog, orders, revenue, and stock — and act on them: discount codes, refunds, cancellations, exchanges, and stock corrections.',
    pills: ['Stock & orders', 'Discount codes', 'Refunds & cancellations', 'Catalog sync'],
  },
  {
    Icon: SiMeta,
    name: 'Meta Ads',
    badge: 'ads_mcp',
    color: '#0082FB',
    desc: 'Campaigns launched, paused, and resumed by the Marketing Agent, with spend guarded by Finance. Budgets never scale on a channel with no evidence it\'s working.',
    pills: ['Campaign launch', 'Auto pause', 'Budget sign-off'],
  },
  {
    Icon: SiInstagram,
    name: 'Instagram',
    badge: 'social_mcp',
    color: '#E1306C',
    desc: 'Publishes AI-generated, on-brand posts and content calendars. The Customer Support Agent also reads and resolves Instagram DMs.',
    pills: ['Post publishing', 'Content scheduling', 'DM resolution'],
  },
  {
    Icon: SiWhatsapp,
    name: 'WhatsApp',
    badge: 'notify_mcp',
    color: '#25D366',
    desc: 'The customer-facing support channel, plus supplier order confirmations and instant brand-owner alerts for critical stockouts and delays.',
    pills: ['Customer support', 'Supplier messages', 'Founder alerts'],
  },
  {
    Icon: SiGoogle,
    name: 'Google & News',
    badge: 'research_mcp',
    color: '#4285F4',
    desc: 'Web search, news coverage, and Google Trends feed the Research Agent — real external signals for trends, competitors, and pricing intelligence.',
    pills: ['Web search', 'News coverage', 'Trend signals'],
  },
  {
    Icon: SiRedis,
    name: 'Redis',
    badge: 'runtime',
    color: '#DC382D',
    desc: 'The runtime backbone — schedules runs, streams agent activity live to the office, and persists long-term brand memory between conversations.',
    pills: ['Scheduling', 'Live streaming', 'Agent memory'],
  },
]

// ── Marquee items ─────────────────────────────────────────────────────────────
export const marqueeItems = [
  { Icon: SiShopify,   label: 'Shopify',      color: '#96BF48' },
  { Icon: SiMeta,      label: 'Meta Ads',     color: '#0082FB' },
  { Icon: SiInstagram, label: 'Instagram',    color: '#E1306C' },
  { Icon: SiFacebook,  label: 'Facebook',     color: '#1877F2' },
  { Icon: SiWhatsapp,  label: 'WhatsApp',     color: '#25D366' },
  { Icon: SiTiktok,    label: 'TikTok',       color: '#69C9D0' },
  { Icon: SiGoogle,    label: 'Google & News', color: '#4285F4' },
  { Icon: SiRedis,     label: 'Redis',        color: '#DC382D' },
]

// ── The Command Center: supervisor + office floor plan ────────────────────────
export const supervisor = {
  title: 'The Supervisor',
  role: 'Chief Executive Agent',
  color: '#d4d4d8',
  desc: 'The LangGraph brain of the platform. It reads brand memory, plans every run, and delegates to the eight operators — chaining them across domains and consulting Finance before any big spend.',
  bullets: [
    'Long-term brand memory that persists across every conversation',
    'Chains agents across domains — research feeds marketing, sales feeds inventory',
    'Consults the Finance Agent before large orders or ad-budget increases',
  ],
}

// Mirrors the real 3D office layout in src/pages/office — pods under the glass office.
export const officePods = [
  {
    name: 'Demand',
    blurb: 'Market & customer facing',
    desks: [
      { label: 'Research', role: 'Market Intelligence', color: '#a855f7' },
      { label: 'Sales',    role: 'Revenue & Growth',    color: '#60a5fa' },
    ],
  },
  {
    name: 'Ops',
    blurb: 'Procurement & stock',
    desks: [
      { label: 'Supplier',  role: 'Procurement', color: '#38bdf8' },
      { label: 'Inventory', role: 'Operations',  color: '#22c55e' },
    ],
  },
  {
    name: 'Growth',
    blurb: 'Brand & revenue',
    desks: [
      { label: 'Finance',   role: 'Finance',           color: '#facc15' },
      { label: 'Marketing', role: 'Brand & Marketing', color: '#f97316' },
    ],
  },
]

// ── How it works steps ────────────────────────────────────────────────────────
export const howItWorksSteps = [
  {
    step: '01',
    title: 'Connect Shopify & Meta',
    desc: 'Link your store and ad account via OAuth. Agents immediately get live read-write access to your catalog, orders, revenue, and campaigns. Works across multiple brands from day one.',
  },
  {
    step: '02',
    title: 'The Supervisor plans, agents execute',
    desc: 'The deep-agent supervisor reads your brand memory and plans each run, then delegates to the eight operators. Each runs its own LangGraph pipeline — placing orders, publishing posts, and launching campaigns, with guardrails.',
  },
  {
    step: '03',
    title: 'Finance protects the margins',
    desc: 'Before any large purchase order or ad-budget increase, the Finance Agent checks affordability, forecasts cash, and computes real product margins. Every budget recommendation is recorded and visible on the dashboard.',
  },
  {
    step: '04',
    title: 'Chat with your AI supervisor',
    desc: 'Ask FashionOS anything in natural language. It holds long-term brand memory, reads live pipeline results, and can spawn and chain the eight agents in a single conversation.',
  },
  {
    step: '05',
    title: 'Watch the Command Center',
    desc: 'The virtual office streams every agent\'s live activity — the tools they call and what they execute — across the demand, ops, and growth pods under the supervisor\'s glass office.',
  },
  {
    step: '06',
    title: 'Customer support on autopilot',
    desc: 'Support resolves real customer issues on WhatsApp, Instagram DM, email, and embedded webchat — refunds, exchanges, cancellations, and tickets — under your actual policy, escalating when limits are hit.',
  },
]