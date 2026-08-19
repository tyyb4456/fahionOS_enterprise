"""
Lightweight, dependency-light merchandising analytics for the Product
Agent — opportunity scoring, initial production quantity, and variant-mix
ranking. Same philosophy as agents/inventory/forecasting.py,
agents/sales/analytics.py, agents/finance/analytics.py,
agents/research/analytics.py, agents/supplier/analytics.py: deterministic
math the LLM shouldn't be eyeballing, not a replacement for real demand
modeling.

score_product_opportunity mirrors the design doc's JSON shape almost
exactly (market_demand, brand_fit, competition, supplier_feasibility,
expected_margin, recommended) — market_demand/competition/supplier_
feasibility/expected_margin are computed from hard inputs; brand_fit is
deliberately NOT computed here — it needs retrieve_policy (brand strategy)
context an LLM has to actually read, so the agent supplies that one itself
(same reasoning as Research's score_product_opportunity, which leaves the
LLM to supply `reason` from real tool-call evidence rather than faking a
number for it).
"""
from __future__ import annotations

from typing import Optional


def calculate_expected_margin(unit_cost: Optional[float], target_price: Optional[float]) -> Optional[float]:
    if unit_cost is None or not target_price:
        return None
    return round((target_price - unit_cost) / target_price, 3)


def score_product_opportunity(
    growth_pct: Optional[float],
    competitor_count: int,
    brand_fit: float,
    supplier_lead_time_days: Optional[int] = None,
    supplier_reliability: Optional[float] = None,
    unit_cost: Optional[float] = None,
    target_price: Optional[float] = None,
) -> dict:
    market_demand = max(0.0, min((growth_pct or 0.0) / 150.0, 1.0))  # normalize, cap at 150% growth = 1.0

    if competitor_count <= 1:
        competition = 0.9
    elif competitor_count <= 4:
        competition = 0.55
    else:
        competition = 0.25

    if supplier_lead_time_days is None or supplier_reliability is None:
        supplier_feasibility = 0.5  # unknown — neutral, agent should flag this in its reason
    else:
        lead_time_component = max(0.0, min(1.0, 1.0 - (supplier_lead_time_days / 45.0)))
        supplier_feasibility = round(lead_time_component * 0.4 + supplier_reliability * 0.6, 2)

    expected_margin = calculate_expected_margin(unit_cost, target_price)
    margin_component = max(0.0, min(1.0, (expected_margin or 0.0) / 0.6)) if expected_margin is not None else 0.5

    brand_fit = max(0.0, min(1.0, brand_fit))

    composite = round(
        market_demand * 0.25 + brand_fit * 0.25 + competition * 0.15 +
        supplier_feasibility * 0.15 + margin_component * 0.20,
        3,
    )

    recommended = composite >= 0.6 and brand_fit >= 0.5 and (expected_margin is None or expected_margin >= 0.25)

    return {
        "market_demand": round(market_demand, 2),
        "brand_fit": round(brand_fit, 2),
        "competition": round(competition, 2),
        "supplier_feasibility": round(supplier_feasibility, 2),
        "expected_margin": expected_margin,
        "composite_score": composite,
        "recommended": recommended,
    }


def estimate_initial_production_quantity(
    estimated_monthly_demand_units: float,
    moq: Optional[int] = None,
    launch_months_cover: int = 2,
    safety_buffer_pct: float = 0.15,
) -> dict:
    base = max(0.0, estimated_monthly_demand_units) * launch_months_cover
    with_buffer = base * (1 + safety_buffer_pct)
    recommended = int(round(with_buffer))
    below_moq = bool(moq) and recommended < moq
    if below_moq:
        recommended = moq
    return {
        "recommended_initial_quantity": recommended,
        "months_covered": launch_months_cover,
        "below_moq_adjusted": below_moq,
        "moq": moq,
    }


def rank_variant_mix(variant_sales: list[dict], cut_threshold_pct: float = 5.0, star_threshold_pct: float = 30.0) -> list[dict]:
    """variant_sales: [{"variant": "Black", "units": 450, "revenue": 1800000}, ...].
    Returns each row + unit/revenue share % + a keep/cut/expand call —
    the real numbers behind "Black = 45% of sales, cut Red" decisions."""
    total_units = sum(max(0, v.get("units", 0)) for v in variant_sales) or 1
    total_revenue = sum(max(0.0, v.get("revenue", 0.0)) for v in variant_sales) or 1e-6

    ranked = []
    for v in variant_sales:
        units = max(0, v.get("units", 0))
        revenue = max(0.0, v.get("revenue", 0.0))
        unit_share = round(units / total_units * 100, 1)
        revenue_share = round(revenue / total_revenue * 100, 1)

        if revenue_share >= star_threshold_pct:
            recommendation = "star — consider expanding"
        elif revenue_share < cut_threshold_pct:
            recommendation = "cut candidate — low share"
        else:
            recommendation = "keep"

        ranked.append({
            "variant": v.get("variant", ""),
            "units": units,
            "revenue": round(revenue, 2),
            "unit_share_pct": unit_share,
            "revenue_share_pct": revenue_share,
            "recommendation": recommendation,
        })

    ranked.sort(key=lambda r: -r["revenue_share_pct"])
    return ranked