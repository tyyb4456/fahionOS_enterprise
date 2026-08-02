import {
  Package, TrendingUp, DollarSign, RotateCcw,
  Megaphone, MessageCircle, RefreshCw, Brain,
} from 'lucide-react'
import {
  SiMeta, SiInstagram, SiFacebook, SiWhatsapp,
  SiShopify, SiGoogle, SiTiktok, SiRedis,
} from '@icons-pack/react-simple-icons'

// ── 8 agents in exact pipeline execution order ───────────────────────────────
export const agents = [
  {
    step: '01',
    icon: Package,
    title: 'Inventory',
    badge: 'inventory-agent',
    desc: 'Real-time Shopify stock sweep. Flags critical stockouts, velocity anomalies, dead stock (45+ days), and size distribution issues specific to Pakistani fashion.',
    color: '#ADDFF1',
    autoExec: true,
  },
  {
    step: '02',
    icon: TrendingUp,
    title: 'Trend',
    badge: 'trend-agent',
    desc: 'Apify scrapes TikTok & Instagram hashtags (#PakistaniFashion, #FashionTikTokPK). Google Trends via Pytrends cross-references catalog SKUs. Runs before Pricing so signals are ready.',
    color: '#9dd6ed',
    autoExec: true,
  },
  {
    step: '03',
    icon: DollarSign,
    title: 'Pricing',
    badge: 'pricing-agent',
    desc: 'Automated markdown and surge pricing in PKR. Auto-executes changes under 15% directly via Shopify MCP. Anything above goes to your Approvals queue.',
    color: '#ADDFF1',
    autoExec: false,
    threshold: '<15% auto',
  },
  {
    step: '04',
    icon: RefreshCw,
    title: 'Restock',
    badge: 'restock-agent',
    desc: 'Predicts days-of-stock for each SKU using velocity data. Generates supplier messages for Lahore/Faisalabad mills with lead times built in. Sends WhatsApp on approval.',
    color: '#9dd6ed',
    autoExec: false,
  },
  {
    step: '05',
    icon: MessageCircle,
    title: 'Content',
    badge: 'content-agent',
    desc: 'Generates Instagram captions and TikTok scripts in Urdu-English mix, timed to PST peak hours. Trending SKUs get urgent posts. Posts directly to your feed after approval.',
    color: '#ADDFF1',
    autoExec: false,
  },
  {
    step: '06',
    icon: RotateCcw,
    title: 'Returns',
    badge: 'returns-agent',
    desc: 'Detects return patterns by SKU and reason (sizing, quality, mismatch). Surfaces structured insights with fix_type recommendations — update size guides, photos, or descriptions.',
    color: '#9dd6ed',
    autoExec: true,
  },
  {
    step: '07',
    icon: Megaphone,
    title: 'Marketing',
    badge: 'marketing-agent',
    desc: 'Monitors Meta campaign ROAS and CPM. Auto-pauses underperformers and decreases budgets. Budget increases and activations need your sign-off — synced with pricing clearance flags.',
    color: '#ADDFF1',
    autoExec: false,
  },
  {
    step: '08',
    icon: MessageCircle,
    title: 'DM',
    badge: 'dm-agent',
    desc: 'Polls Facebook Page & Instagram DMs. Classifies bulk inquiries, complaints, and compliments. Drafts replies and routes urgent threads to your review queue.',
    color: '#9dd6ed',
    autoExec: true,
  },
]

// ── Stats ─────────────────────────────────────────────────────────────────────
export const stats = [
  { value: '8',   label: 'Specialized Agents', suffix: '' },
  { value: '24',  label: 'Hour Automation',     suffix: '/7' },
  { value: '<15', label: 'Auto-exec Threshold', suffix: '%' },
  { value: '2',   label: 'Agent Layers',        suffix: '' },
]

// ── Platform integrations (Shopify + Meta stack) ──────────────────────────────
export const integrations = [
  {
    Icon: SiShopify,
    name: 'Shopify',
    badge: 'shopify_mcp',
    color: '#96BF48',
    desc: 'Primary data source. OAuth connects your store — agents read catalog, orders, and inventory in real time. Webhooks trigger selective agent runs on orders and refunds.',
    pills: ['OAuth flow', 'Webhooks', 'Price writes', 'Catalog sync'],
  },
  {
    Icon: SiMeta,
    name: 'Meta Ads',
    badge: 'ads_mcp',
    color: '#0082FB',
    desc: 'Reads campaign ROAS, CPM, and ad-set performance across your account. Marketing agent auto-pauses poor performers and flags budget increases for your approval.',
    pills: ['Campaign ROAS', 'Auto-pause', 'Budget control'],
  },
  {
    Icon: SiInstagram,
    name: 'Instagram',
    badge: 'social_mcp',
    color: '#E1306C',
    desc: 'Posts AI-generated content directly to your feed. Monitors story engagement and hashtag reach. DM agent reads and drafts replies to Instagram messages.',
    pills: ['Content posting', 'DM replies', 'Hashtag signals'],
  },
  {
    Icon: SiFacebook,
    name: 'Facebook',
    badge: 'social_mcp',
    color: '#1877F2',
    desc: 'Reads Page DMs and manages customer interactions. Surfaces complaint threads and bulk order inquiries into the DM Autopilot queue for your review.',
    pills: ['Page DMs', 'Complaint detection', 'Order inquiries'],
  },
  {
    Icon: SiWhatsapp,
    name: 'WhatsApp',
    badge: 'notify_mcp',
    color: '#25D366',
    desc: 'Delivers critical stockout alerts, restock approval nudges, and daily pipeline digests straight to your phone. Supplier messages for approved restock orders go here too.',
    pills: ['Critical alerts', 'Daily digest', 'Supplier messages'],
  },
]

// ── Marquee items ─────────────────────────────────────────────────────────────
export const marqueeItems = [
  { Icon: SiShopify,   label: 'Shopify',       color: '#96BF48' },
  { Icon: SiMeta,      label: 'Meta Ads',       color: '#0082FB' },
  { Icon: SiInstagram, label: 'Instagram',      color: '#E1306C' },
  { Icon: SiFacebook,  label: 'Facebook',       color: '#1877F2' },
  { Icon: SiWhatsapp,  label: 'WhatsApp',       color: '#25D366' },
  { Icon: SiTiktok,    label: 'TikTok',         color: '#69C9D0' },
  { Icon: SiGoogle,    label: 'Google Trends',  color: '#4285F4' },
  { Icon: SiRedis,     label: 'Redis',          color: '#DC382D' },
]

// ── Inline SVG icon for Apify ─────────────────────────────────────────────────
const ApifyIcon = ({ size, color }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path
      d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)

// ── Trend sources ─────────────────────────────────────────────────────────────
export const trendSources = [
  {
    id: 'apify',
    label: 'Apify',
    badge: 'social_mcp',
    color: '#00C4B4',
    icon: ApifyIcon,
    platforms: [
      { PIcon: SiTiktok,    name: 'TikTok',    posts: '15 posts / hashtag', color: '#69C9D0' },
      { PIcon: SiInstagram, name: 'Instagram', posts: '10 posts / hashtag', color: '#E1306C' },
    ],
    bullets: [
      { stat: '4',   unit: 'hashtags',   desc: 'scraped per run (top 2 TikTok, top 2 IG)' },
      { stat: 'PK',  unit: 'geo-locked', desc: 'Pakistan region targeting only' },
      { stat: '24h', unit: 'cached',     desc: 'results cached to protect quota' },
    ],
    desc: 'Apify cloud actors scrape real post data from TikTok and Instagram hashtags — views, likes, captions, and engagement signals — without hitting platform API rate limits.',
    pills: ['#PakistaniFashion', '#FashionTikTokPK', '#PakistaniOutfits', 'GRWM'],
    pillLabel: 'Monitored hashtags',
  },
  {
    id: 'gtrends',
    label: 'Google Trends',
    badge: 'trends_mcp',
    color: '#4285F4',
    icon: ({ size }) => <SiGoogle size={size} color="#4285F4" />,
    platforms: [
      { PIcon: SiGoogle, name: 'Pytrends', posts: 'free · no quota', color: '#4285F4' },
    ],
    bullets: [
      { stat: '5',  unit: 'keywords', desc: 'compared per run (3 base + 2 from catalog)' },
      { stat: '7d', unit: 'window',   desc: 'rolling week for recency-weighted signals' },
      { stat: '0',  unit: 'cost',     desc: 'free via Pytrends — no API key needed' },
    ],
    desc: 'Pytrends pulls keyword interest-over-time data from Google Trends and cross-references it with catalog SKU names to surface rising demand before competitors react.',
    pills: ['lawn suit', 'co-ord set', 'cargo pants', 'linen kurta', 'modest fashion'],
    pillLabel: 'Base keywords',
  },
]

// ── How it works steps ────────────────────────────────────────────────────────
export const howItWorksSteps = [
  {
    step: '01',
    title: 'Connect Shopify & Meta',
    desc: 'Link your Shopify store and Meta ad account via OAuth. Agents immediately read your catalog, orders, and ad campaigns. Shopify webhooks trigger selective runs on new orders and refunds.',
  },
  {
    step: '02',
    title: 'Pipeline runs on schedule',
    desc: 'Celery + Redis schedules hourly inventory sweeps and full daily pipeline runs across all 8 agents. The LangGraph supervisor decides which agents to activate based on the trigger type.',
  },
  {
    step: '03',
    title: 'Review the Approvals queue',
    desc: 'High-stakes decisions (price changes ≥15%, restock orders, ad budget increases, content posts) land in your queue with full context — inventory position, trend signals, ROAS. One tap to approve or reject.',
  },
  {
    step: '04',
    title: 'Chat with your AI supervisor',
    desc: 'Ask FashionOS anything in natural language. The deep agent supervisor has brand-specific long-term memory, DB access to all pipeline results, and can spawn live Shopify and Meta subagents.',
  },
  {
    step: '05',
    title: 'Get WhatsApp alerts',
    desc: 'Critical stockouts, approval reminders, approved restock supplier messages, and daily pipeline digests land straight on your phone via WhatsApp.',
  },
]