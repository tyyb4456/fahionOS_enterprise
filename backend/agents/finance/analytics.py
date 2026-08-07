"""
Lightweight, dependency-light financial analytics for the Finance Agent —
profit/margin math, a cashflow projection, product margin ranking, ROI,
and a purchase-order affordability check.

Same philosophy as agents/inventory/forecasting.py and
agents/sales/analytics.py: good enough to unblock the agent today without
a real accounting/forecasting engine.

Note on "cash": this codebase has no bank/Stripe/PayPal balance
integration (see db/models.py::Brand — only Shopify/Meta/Instagram
credentials exist), so "current cash" here is a proxy: the running net of
(revenue - expenses - refunds) over the lookback window, not a real bank
balance. Treat forecast_cashflow's numbers as directional, not exact —
the Finance Agent's system prompt tells it to say so explicitly.
"""
from __future__ import annotations

from typing import Optional

import numpy as np


def calculate_profit(revenue: float, expenses: float, refunds: float = 0.0) -> dict:
    profit = revenue - expenses - refunds
    margin = round((profit / revenue) * 100, 2) if revenue else 0.0
    return {
        "revenue": round(revenue, 2), "expenses": round(expenses, 2), "refunds": round(refunds, 2),
        "profit": round(profit, 2), "margin_pct": margin,
    }


def calculate_margin(cost_price: Optional[float], selling_price: float) -> Optional[float]:
    """Gross margin % for one SKU. None if cost_price isn't on file."""
    if cost_price is None or selling_price <= 0:
        return None
    return round(((selling_price - cost_price) / selling_price) * 100, 2)


def rank_products_by_margin(variants: list[dict], top_n: int = 10) -> dict:
    """variants: [{"sku", "title", "price", "cost_price", "inventory_quantity"}, ...].
    Splits into ranked (has cost_price) and variants_missing_cost_price (doesn't)."""
    ranked: list[dict] = []
    missing: list[dict] = []
    for v in variants:
        margin_pct = calculate_margin(v.get("cost_price"), v.get("price", 0))
        if margin_pct is None:
            missing.append({"sku": v.get("sku"), "title": v.get("title")})
            continue
        ranked.append({
            "sku": v.get("sku"), "title": v.get("title"), "price": v.get("price"),
            "cost_price": v.get("cost_price"), "margin_pct": margin_pct,
            "inventory_quantity": v.get("inventory_quantity", 0),
        })
    ranked.sort(key=lambda r: -r["margin_pct"])
    return {
        "best_margin": ranked[:top_n],
        "worst_margin": list(reversed(ranked[-top_n:])) if len(ranked) > top_n else list(reversed(ranked)),
        "variants_missing_cost_price": missing,
    }


def calculate_roi(spend: float, revenue: float) -> dict:
    if spend <= 0:
        return {"spend": spend, "revenue": revenue, "roi_pct": None, "message": "Spend must be > 0 to compute ROI."}
    roi_pct = round(((revenue - spend) / spend) * 100, 2)
    return {"spend": round(spend, 2), "revenue": round(revenue, 2), "roi_pct": roi_pct}


def forecast_cashflow(current_cash: float, daily_net_cash_flow_history: list[dict], forecast_days: int = 30) -> dict:
    """Same weighted-moving-average + linear-trend approach as
    agents/sales/analytics.py::forecast_revenue, applied to net daily cash
    flow (revenue - expenses - refunds) instead of revenue alone."""
    values = [float(d.get("net_cash_flow", 0.0)) for d in daily_net_cash_flow_history]
    if not values:
        return {
            "cash_today": round(current_cash, 2), "predicted_cash": round(current_cash, 2),
            "predicted_revenue": 0.0, "predicted_expenses": 0.0,
            "risk": "medium", "confidence": 0.2,
        }

    n = len(values)
    weights = np.linspace(1.0, 2.0, num=n)
    weighted_avg = float(np.average(values, weights=weights))

    slope = 0.0
    if n >= 4:
        x = np.arange(n)
        slope, _ = np.polyfit(x, values, 1)

    projected_daily_net = weighted_avg + slope * (forecast_days / 2)
    predicted_cash = round(current_cash + projected_daily_net * forecast_days, 2)

    variance = float(np.var(values)) if n > 1 else 0.0
    mean = abs(weighted_avg) or 1e-6
    coefficient_of_variation = (variance ** 0.5) / mean
    confidence = max(0.2, min(0.95, 1.0 - min(coefficient_of_variation, 1.0) * 0.6 - (0.15 if n < 7 else 0.0)))

    if predicted_cash < 0:
        risk = "critical"
    elif current_cash > 0 and predicted_cash < current_cash * 0.25:
        risk = "high"
    elif projected_daily_net < 0:
        risk = "medium"
    else:
        risk = "low"

    predicted_revenue = round(max(0.0, projected_daily_net) * forecast_days, 2)
    predicted_expenses = round(max(0.0, -projected_daily_net) * forecast_days, 2)

    return {
        "cash_today": round(current_cash, 2),
        "predicted_cash": predicted_cash,
        "predicted_revenue": predicted_revenue,     # net-flow based, directional only
        "predicted_expenses": predicted_expenses,
        "risk": risk,
        "confidence": round(confidence, 2),
    }


def evaluate_purchase_order(po: dict, current_cash: float, safety_buffer_pct: float = 0.2) -> dict:
    """Advisory affordability check — NOT a write. `po` comes from
    crud_finance.get_purchase_order_cost(); safety_buffer_pct is the
    fraction of current cash that must remain untouched after the order."""
    total_cost = po.get("total_cost")
    if total_cost is None:
        return {
            "purchase_order_id": po.get("purchase_order_id"), "sku": po.get("sku"), "approved": None,
            "approved_budget": None,
            "reason": f"No cost_price on file for SKU '{po.get('sku')}' — can't evaluate affordability. "
                      "Set a cost_price for this variant before ordering, or ask the founder for the unit cost.",
            "conditions": [],
        }

    safety_floor = current_cash * safety_buffer_pct
    remaining_after = current_cash - total_cost

    if total_cost <= 0:
        approved, reason = True, "Zero-cost order."
    elif remaining_after >= safety_floor:
        approved = True
        reason = (
            f"Order cost {total_cost} leaves {round(remaining_after, 2)} in reserve, "
            f"above the {int(safety_buffer_pct * 100)}% safety floor of {round(safety_floor, 2)}."
        )
    else:
        approved = False
        reason = (
            f"Order cost {total_cost} would drop reserves to {round(remaining_after, 2)}, "
            f"below the {int(safety_buffer_pct * 100)}% safety floor of {round(safety_floor, 2)}."
        )

    conditions = [] if approved else [
        "Delay the order until cash position improves, or negotiate a smaller/split quantity with the supplier.",
    ]

    return {
        "purchase_order_id": po.get("purchase_order_id"), "sku": po.get("sku"),
        "approved": approved, "approved_budget": total_cost if approved else None,
        "reason": reason, "conditions": conditions,
    }