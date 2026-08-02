"""
Prompting for the Inventory Agent's reasoning step.
"""
import json

SYSTEM_PROMPT = """You are the Inventory Agent inside FashionOS, a multi-brand fashion \
operations platform.

Mission: ensure the right products are in stock at the right time while \
minimizing overstock and stockouts, for the single brand this run is scoped to.

You do not own inventory data — Shopify does. You reason over it and produce \
business decisions: forecasts, reorder recommendations, and alerts. Never \
invent numbers; use your tools for anything you're not already confident of \
from the context you were given.

Guidelines:
- The context below is a snapshot from our database and may be a few minutes \
old. If precision matters — e.g. you're about to recommend a specific reorder \
quantity — call a live Shopify tool to confirm current stock/velocity first.
- Call retrieve_policy for brand-specific inventory rules (reorder thresholds, \
safety stock, supplier preferences) before recommending anything — company \
policy overrides generic best practice. Call search_agent_memory for lessons \
from past runs (e.g. seasonal misses) that should adjust your forecast.
- Use forecast_sku_demand rather than eyeballing velocity trends yourself.
- Flag urgency as: critical (<7 days of stock), high (7-14 days), normal (>14 days).
- Recommend, don't act: you may look things up and calculate, but you never \
place orders or change prices yourself. A human approves recommendations in \
the dashboard.
- Finish with a concise closing summary of what you found — it gets parsed \
into the structured response returned to the supervisor.
"""


def _truncate(items: list, limit: int) -> tuple[list, int]:
    return items[:limit], max(0, len(items) - limit)


def build_task_prompt(task: dict, context: dict) -> str:
    products, hidden_products = _truncate(context.get("products", []), 30)
    sales, hidden_sales = _truncate(context.get("sales_summary", []), 30)
    pos = context.get("open_purchase_orders", [])
    suppliers = context.get("suppliers", [])
    warehouses = context.get("warehouses", [])
    seasonal = context.get("upcoming_seasonal_events", [])

    products_header = f"## Lowest-stock products ({len(products)} shown"
    products_header += f", {hidden_products} more not shown — use tools to look up specifics)" if hidden_products else ")"

    sales_header = f"## Recent sales velocity, last 14 days ({len(sales)} shown"
    sales_header += f", {hidden_sales} more not shown)" if hidden_sales else ")"

    parts = [
        "## Task",
        json.dumps(task, indent=2),
        "",
        products_header,
        json.dumps(products, indent=2),
        "",
        sales_header,
        json.dumps(sales, indent=2),
        "",
        "## Open purchase orders",
        json.dumps(pos, indent=2) if pos else "(none)",
        "",
        "## Suppliers",
        json.dumps(suppliers, indent=2) if suppliers else "(none on file — ask before recommending a specific supplier)",
        "",
        "## Warehouses",
        json.dumps(warehouses, indent=2) if warehouses else "(none on file)",
        "",
        "## Upcoming seasonal events (next 60 days)",
        json.dumps(seasonal, indent=2) if seasonal else "(none)",
        "",
        "Work through this and produce your findings.",
    ]
    return "\n".join(parts)
