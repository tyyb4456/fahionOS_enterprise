"""
Lightweight, dependency-light procurement analytics for the Supplier Agent
— vendor scoring/ranking, total landed cost, and a deterministic quote
estimator (placeholder for a real supplier-portal/RFQ integration). Same
philosophy as agents/inventory/forecasting.py and agents/finance/analytics.py:
good enough to unblock the agent today, not a replacement for a real
supplier-quoting or logistics platform.
"""
from __future__ import annotations

from typing import Optional


def score_supplier(
    unit_price: Optional[float],
    lead_time_days: int,
    reliability_score: float,
    quality_score: float,
    target_price: Optional[float] = None,
) -> float:
    """
    0-100 composite score. Price is scored relative to target_price when
    given (cheaper = better, but not the only factor — see the design
    doc's "it isn't just choosing the cheapest supplier"); lead time is
    scored against a 30-day reference window; reliability/quality come
    straight from the supplier's own track record.
    """
    price_score = 70.0  # neutral default when no target/price to compare
    if unit_price is not None and target_price:
        ratio = unit_price / target_price if target_price else 1.0
        # at or under target => 100, 50% over target => ~0
        price_score = max(0.0, min(100.0, 100.0 - (ratio - 1.0) * 200.0))

    lead_time_score = max(0.0, min(100.0, 100.0 - (lead_time_days / 30.0) * 100.0))
    reliability_component = max(0.0, min(1.0, reliability_score)) * 100.0
    quality_component = max(0.0, min(1.0, quality_score)) * 100.0

    # weights: price 35%, lead time 20%, reliability 25%, quality 20%
    return round(
        price_score * 0.35 + lead_time_score * 0.20 +
        reliability_component * 0.25 + quality_component * 0.20,
        1,
    )


def rank_suppliers(candidates: list[dict], target_price: Optional[float] = None) -> list[dict]:
    """
    candidates: [{"supplier_id", "name", "unit_price"?, "lead_time_days",
    "reliability_score", "quality_score", ...}, ...]. Returns the same
    dicts with a "score" and "reason" attached, sorted best-first.
    """
    ranked = []
    for c in candidates:
        score = score_supplier(
            c.get("unit_price"), c.get("lead_time_days", 14),
            c.get("reliability_score", 0.8), c.get("quality_score", 0.8),
            target_price=target_price,
        )
        reasons = []
        if c.get("lead_time_days", 999) <= 10:
            reasons.append("fast lead time")
        if c.get("reliability_score", 0) >= 0.9:
            reasons.append("highly reliable")
        if target_price and c.get("unit_price") and c["unit_price"] <= target_price:
            reasons.append("at or under target price")
        reason = ", ".join(reasons) if reasons else "best available balance of price, speed, and track record"
        ranked.append({**c, "score": score, "reason": reason.capitalize()})

    ranked.sort(key=lambda r: -r["score"])
    return ranked


def calculate_total_landed_cost(unit_price: float, quantity: int, shipping_cost: float = 0.0, duty_pct: float = 0.0) -> dict:
    goods_cost = unit_price * quantity
    duty = goods_cost * (duty_pct / 100.0)
    total = goods_cost + shipping_cost + duty
    return {
        "goods_cost": round(goods_cost, 2),
        "shipping_cost": round(shipping_cost, 2),
        "duty": round(duty, 2),
        "total_cost": round(total, 2),
        "unit_landed_cost": round(total / quantity, 2) if quantity else 0.0,
    }


def estimate_quote(base_price: Optional[float], quantity: int, moq: int, lead_time_days: int) -> dict:
    """
    Deterministic quote placeholder used by request_quotes when there's no
    live supplier-portal/RFQ-response integration yet (see
    agents/supplier/tools.py). Applies a simple volume discount above MOQ
    and flags when the requested quantity is below the supplier's MOQ.
    Swap this for a real RFQ-response ingestion pipeline later — its
    signature and return shape are the contract tools.py depends on, not
    the pricing model itself.
    """
    price = float(base_price) if base_price else 0.0
    if moq and quantity >= moq * 3:
        price *= 0.90
    elif moq and quantity >= moq * 2:
        price *= 0.95

    below_moq = bool(moq) and quantity < moq
    return {
        "unit_price": round(price, 2),
        "quantity": quantity,
        "moq": moq,
        "lead_time_days": lead_time_days,
        "below_moq": below_moq,
        "note": (
            f"Requested quantity is below this supplier's MOQ of {moq}." if below_moq
            else "Estimated from the supplier's on-file pricing and volume tiers."
        ),
    }


def update_reliability_score(current_score: float, positive_outcome: bool, weight: float = 0.15) -> float:
    """Exponential-moving-average nudge — one late delivery or quality miss
    shifts the score gradually rather than overreacting to a single data
    point. Used for both reliability_score (on-time delivery) and
    quality_score (no quality issue found)."""
    target = 1.0 if positive_outcome else 0.0
    new_score = current_score + (target - current_score) * weight
    return round(max(0.0, min(1.0, new_score)), 3)