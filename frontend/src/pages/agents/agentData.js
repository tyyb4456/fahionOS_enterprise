import {
  Package, TrendingUp, Megaphone, Coins, FlaskConical, Truck, Headphones,
} from 'lucide-react'

// Per-agent command-center configuration. Every section maps 1:1 to a
// read endpoint in backend/api/routers/agents/*.py; `runBody` is the
// default payload for the manual POST /run trigger.

export const AGENTS = [
  {
    id: 'inventory',
    label: 'Inventory',
    color: '#22c55e',
    Icon: Package,
    role: 'Stock levels, alerts, reorder recommendations',
    runBody: { task_type: 'forecast_inventory' },
    sections: [
      { label: 'Alerts', path: '/api/v1/agents/inventory/alerts' },
      { label: 'Reorder recommendations', path: '/api/v1/agents/inventory/recommendations' },
    ],
  },
  {
    id: 'sales',
    label: 'Sales',
    color: '#60a5fa',
    Icon: TrendingUp,
    role: 'Revenue, reports, forecasts & anomalies',
    runBody: { task_type: 'analyze_sales', time_range: 'last_7_days' },
    sections: [
      { label: 'Insights', path: '/api/v1/agents/sales/insights' },
      { label: 'KPI reports', path: '/api/v1/agents/sales/reports' },
      { label: 'Revenue forecasts', path: '/api/v1/agents/sales/forecasts' },
      { label: 'Anomalies', path: '/api/v1/agents/sales/anomalies' },
      { label: 'Customer segments', path: '/api/v1/agents/sales/customer-segments' },
    ],
  },
  {
    id: 'marketing',
    label: 'Marketing',
    color: '#f97316',
    Icon: Megaphone,
    role: 'Campaigns, content plans & performance',
    runBody: { task_type: 'plan_marketing' },
    sections: [
      { label: 'Campaigns', path: '/api/v1/agents/marketing/campaigns' },
      { label: 'Content plans', path: '/api/v1/agents/marketing/content-plans' },
      { label: 'Scheduled content', path: '/api/v1/agents/marketing/scheduled-content' },
      { label: 'Insights', path: '/api/v1/agents/marketing/insights' },
      { label: 'Audience segments', path: '/api/v1/agents/marketing/audience-segments' },
      { label: 'Content performance', path: '/api/v1/agents/marketing/content-performance' },
    ],
  },
  {
    id: 'finance',
    label: 'Finance',
    color: '#facc15',
    Icon: Coins,
    role: 'P&L, cashflow, expenses & risk',
    runBody: { task_type: 'financial_analysis', time_range: 'last_30_days' },
    sections: [
      { label: 'Financial reports', path: '/api/v1/agents/finance/reports' },
      { label: 'Cashflow forecasts', path: '/api/v1/agents/finance/forecasts' },
      { label: 'Insights', path: '/api/v1/agents/finance/insights' },
      { label: 'Budget recommendations', path: '/api/v1/agents/finance/budget-recommendations' },
      { label: 'Risk assessments', path: '/api/v1/agents/finance/risk-assessments' },
      { label: 'Expenses', path: '/api/v1/agents/finance/expenses' },
    ],
  },
  {
    id: 'research',
    label: 'Research',
    color: '#a855f7',
    Icon: FlaskConical,
    role: 'Trends, competitors & product opportunities',
    runBody: { task_type: 'trend_monitoring' },
    sections: [
      { label: 'Market trends', path: '/api/v1/agents/research/trends' },
      { label: 'Competitor analyses', path: '/api/v1/agents/research/competitors' },
      { label: 'Product opportunities', path: '/api/v1/agents/research/opportunities' },
      { label: 'Pricing intelligence', path: '/api/v1/agents/research/pricing' },
      { label: 'Insights', path: '/api/v1/agents/research/insights' },
    ],
  },
  {
    id: 'supplier',
    label: 'Supplier',
    color: '#38bdf8',
    Icon: Truck,
    role: 'Purchase orders, quotes & supplier scores',
    runBody: { task_type: 'evaluate_suppliers' },
    sections: [
      { label: 'Purchase orders', path: '/api/v1/agents/supplier/purchase-orders' },
      { label: 'Quotes', path: '/api/v1/agents/supplier/quotes' },
      { label: 'Negotiations', path: '/api/v1/agents/supplier/negotiations' },
      { label: 'Insights', path: '/api/v1/agents/supplier/insights' },
      { label: 'Suppliers', path: '/api/v1/agents/supplier/suppliers' },
    ],
  },
  {
    id: 'customer_support',
    label: 'Customer Support',
    color: '#e879f9',
    Icon: Headphones,
    role: 'Tickets, conversations & feedback',
    runBody: { task_type: 'escalation_review' },
    sections: [
      { label: 'Tickets', path: '/api/v1/agents/customer-support/tickets' },
      { label: 'Conversations', path: '/api/v1/agents/customer-support/conversations' },
      { label: 'Refunds', path: '/api/v1/agents/customer-support/refunds' },
      { label: 'Exchanges', path: '/api/v1/agents/customer-support/exchanges' },
      { label: 'Insights', path: '/api/v1/agents/customer-support/insights' },
      { label: 'Customer feedback', path: '/api/v1/agents/customer-support/feedback' },
    ],
  },
]

export function agentById(id) {
  return AGENTS.find(a => a.id === id) || AGENTS[0]
}
