"""
Lightweight analytics for the Sales Agent — revenue/KPI math, anomaly
detection, a simple revenue forecast, ABC product ranking, and RFM-ish
customer segmentation.

Same philosophy as agents/inventory/forecasting.py: dependency-light,
good enough to unblock the agent today, not a replacement for a real BI/
forecasting stack. The shapes returned here are the contract
db/crud_sales.py + agents/sales/tools.py depend on.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np


# ── Revenue / KPI math ───────────────────────────────────────────────────

def calculate_revenue_kpis(
    orders: list[dict],
    returns: list[dict],
    distinct_customers_repeat: int,
    distinct_customers_total: int,
) -> dict:
    """
    orders: [{"total_price": float, ...}, ...] for the period.
    returns: [{"refund_amount": float, ...}, ...] for the same period.
    """
    revenue = float(sum(o.get("total_price", 0.0) for o in orders))
    order_count = len(orders)
    aov = float(round(revenue / order_count, 2)) if order_count else 0.0

    refunded = float(sum(r.get("refund_amount", 0.0) for r in returns))
    refund_rate = float(round(refunded / revenue, 4)) if revenue else 0.0

    repeat_rate = (
        float(round(distinct_customers_repeat / distinct_customers_total, 4))
        if distinct_customers_total else 0.0
    )

    return {
        "revenue": round(revenue, 2),
        "orders": order_count,
        "average_order_value": aov,
        "refund_rate": refund_rate,
        "repeat_customer_rate": repeat_rate,
    }


def percent_change(current: float, previous: float) -> Optional[float]:
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 2)


# ── Anomaly detection ────────────────────────────────────────────────────

def detect_anomaly(daily_series: list[float], metric: str, z_threshold: float = 2.0) -> Optional[dict]:
    """
    Flags the most recent point in a daily series as anomalous if it's more
    than `z_threshold` standard deviations from the series' own mean
    (computed over the earlier points, so today doesn't drag its own
    baseline toward itself). Needs at least 6 points to be meaningful.
    """
    if len(daily_series) < 6:
        return None

    *history, latest = [float(x) for x in daily_series]
    mean = float(np.mean(history))
    std = float(np.std(history))

    if std == 0:
        if latest == mean:
            return None
        z = float("inf")
    else:
        z = (latest - mean) / std

    if abs(z) < z_threshold:
        return None

    severity = "critical" if abs(z) >= 3.5 else ("high" if abs(z) >= 2.75 else "medium")
    direction = "spiked" if z > 0 else "dropped"

    return {
        "metric": metric,
        "expected": round(mean, 2),
        "actual": round(latest, 2),
        "severity": severity,
        "message": (
            f"{metric} {direction} to {round(latest, 2)} vs a recent average of "
            f"{round(mean, 2)} ({round(z, 2)} std deviations)."
        ),
    }


# ── Forecast ──────────────────────────────────────────────────────────────

def forecast_revenue(daily_revenue_history: list[float], forecast_days: int = 7) -> dict:
    """
    Same weighted-moving-average + linear-trend approach as
    forecast_sku_demand in the Inventory Agent — recent days weigh up to 2x
    older days, trend nudges the projection up or down.
    """
    history = [max(0.0, float(x)) for x in daily_revenue_history]
    if not history:
        return {
            "predicted_daily_revenue": 0.0,
            "predicted_revenue_total": 0.0,
            "forecast_days": forecast_days,
            "trend": "unknown",
            "confidence": 0.1,
        }

    n = len(history)
    weights = np.linspace(1.0, 2.0, num=n)
    weighted_avg = float(np.average(history, weights=weights))

    trend = "stable"
    slope = 0.0
    if n >= 4:
        x = np.arange(n)
        slope, _ = np.polyfit(x, history, 1)
        if slope > 0.05 * (weighted_avg + 1e-6):
            trend = "increasing"
        elif slope < -0.05 * (weighted_avg + 1e-6):
            trend = "decreasing"

    projected_daily = max(0.0, float(weighted_avg + slope * (forecast_days / 2)))
    predicted_total = float(round(projected_daily * forecast_days, 2))

    variance = float(np.var(history)) if n > 1 else 0.0
    mean = weighted_avg or 1e-6
    coefficient_of_variation = (variance ** 0.5) / mean
    confidence = max(
        0.2,
        min(0.95, 1.0 - min(coefficient_of_variation, 1.0) * 0.6 - (0.15 if n < 7 else 0.0)),
    )

    return {
        "predicted_daily_revenue": float(round(projected_daily, 2)),
        "predicted_revenue_total": predicted_total,
        "forecast_days": forecast_days,
        "trend": trend,
        "confidence": float(round(confidence, 2)),
    }


# ── ABC product analysis ─────────────────────────────────────────────────

def rank_products_by_revenue(line_items: list[dict], top_n: int = 10) -> tuple[list[dict], list[dict]]:
    """Groups order line items by SKU, sums revenue/units, returns
    (top_n best sellers, top_n worst sellers) sorted by revenue."""
    by_sku: dict[str, dict] = {}
    for item in line_items:
        sku = item.get("sku") or "NO_SKU"
        if sku not in by_sku:
            by_sku[sku] = {"sku": sku, "name": item.get("name", ""), "units": 0, "revenue": 0.0}
        by_sku[sku]["units"] += item.get("quantity", 0)
        by_sku[sku]["revenue"] += float(item.get("price", 0)) * item.get("quantity", 0)

    for row in by_sku.values():
        row["revenue"] = round(row["revenue"], 2)

    ranked = sorted(by_sku.values(), key=lambda r: -r["revenue"])
    top = ranked[:top_n]
    worst = list(reversed(ranked[-top_n:])) if len(ranked) > top_n else list(reversed(ranked))
    return top, worst


# ── Customer segmentation (RFM-ish) ──────────────────────────────────────

_SEGMENT_DEFINITIONS = {
    "VIP":      "Top 10% by lifetime spend among repeat buyers.",
    "Loyal":    "3+ orders, most recent within 60 days.",
    "New":      "First order within the last 30 days.",
    "At Risk":  "2+ past orders but nothing in 90+ days.",
    "Inactive": "No order in 180+ days.",
}


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def segment_customers(customers: list[dict], now: Optional[datetime] = None) -> list[dict]:
    """
    Simple recency/frequency/monetary heuristic — good enough for a first
    pass without a dedicated clustering model. A customer lands in exactly
    one bucket, checked in priority order below.
    """
    now = now or datetime.now(timezone.utc)
    segments: dict[str, list[dict]] = {"VIP": [], "Loyal": [], "New": [], "At Risk": [], "Inactive": []}

    spenders = sorted(
        (c for c in customers if c.get("orders_count", 0) >= 2),
        key=lambda c: -c.get("total_spent", 0.0),
    )
    vip_cutoff = max(1, round(len(spenders) * 0.1)) if spenders else 0
    vip_ids = {c["customer_id"] for c in spenders[:vip_cutoff]}

    for c in customers:
        cid = c.get("customer_id")
        last_order_at = c.get("last_order_at")
        first_order_at = c.get("first_order_at")
        orders_count = c.get("orders_count", 0)

        days_since_last = (now - _as_aware(last_order_at)).days if last_order_at else None
        days_since_first = (now - _as_aware(first_order_at)).days if first_order_at else None

        if cid in vip_ids:
            segments["VIP"].append(c)
        elif days_since_last is not None and days_since_last >= 180:
            segments["Inactive"].append(c)
        elif orders_count >= 2 and days_since_last is not None and days_since_last >= 90:
            segments["At Risk"].append(c)
        elif orders_count >= 3 and days_since_last is not None and days_since_last <= 60:
            segments["Loyal"].append(c)
        elif days_since_first is not None and days_since_first <= 30:
            segments["New"].append(c)
        # single-order, not-yet-classified customers are left out of a
        # named bucket rather than forced into one that doesn't fit.

    return [
        {
            "segment": name,
            "customer_count": len(rows),
            "customer_ids": [str(c.get("customer_id")) for c in rows][:200],
            "definition": _SEGMENT_DEFINITIONS[name],
        }
        for name, rows in segments.items()
        if rows
    ]


# ── Cohort retention ─────────────────────────────────────────────────────

def cohort_retention(orders_by_customer: dict[str, list[datetime]], months_forward: int = 3) -> list[dict]:
    """
    orders_by_customer: {customer_id: [order_created_at, ...]}.

    Groups customers by the calendar month of their first order in the
    queried window (their "cohort"), then reports what % of that cohort
    placed another order in each of the following `months_forward` months.
    """
    def _month_key(dt: datetime) -> str:
        return f"{dt.year:04d}-{dt.month:02d}"

    def _add_months(y: int, m: int, n: int) -> tuple[int, int]:
        total = (m - 1) + n
        return y + total // 12, total % 12 + 1

    cohorts: dict[str, set[str]] = {}
    order_months: dict[str, set[str]] = {}

    for cid, dates in orders_by_customer.items():
        if not dates:
            continue
        months = sorted({_month_key(d) for d in dates})
        cohort_key = months[0]
        cohorts.setdefault(cohort_key, set()).add(cid)
        order_months[cid] = set(months)

    result = []
    for cohort_key, members in sorted(cohorts.items()):
        y, m = int(cohort_key[:4]), int(cohort_key[5:7])
        row = {"cohort": cohort_key, "cohort_size": len(members)}
        for n in range(1, months_forward + 1):
            ny, nm = _add_months(y, m, n)
            target = f"{ny:04d}-{nm:02d}"
            retained = sum(1 for cid in members if target in order_months.get(cid, set()))
            row[f"month_{n}_retention_pct"] = round(retained / len(members) * 100, 1) if members else 0.0
        result.append(row)

    return result