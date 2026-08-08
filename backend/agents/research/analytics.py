"""
Lightweight, dependency-light scoring helpers for the Research Agent —
turns raw signals (trend growth %, how many competitors already sell
something, whether we already carry it) into the market_score/competition/
priority fields on a product opportunity, and ranks a batch of trends.
Same philosophy as agents/inventory/forecasting.py, agents/sales/analytics.py,
agents/marketing/analytics.py, agents/finance/analytics.py: deterministic
math the LLM shouldn't be eyeballing, not a replacement for real trend/
demand modeling.
"""
from __future__ import annotations

from typing import Literal, Optional


def score_product_opportunity(
    growth_pct: Optional[float],
    competitor_count: int,
    we_already_sell: bool,
) -> dict:
    """
    growth_pct: external demand growth signal (e.g. from google_trends_search
        or a competitor's reported sales growth), 0-100+ scale. None if unknown.
    competitor_count: how many competitors researched are already selling this.
    we_already_sell: whether search_our_catalog found a matching product.
    """
    if we_already_sell:
        return {
            "market_score": 0.0, "competition": "n/a", "priority": "low",
            "reason": "Already in our catalog — this is a promotion/pricing question, not a launch opportunity.",
        }

    growth = max(0.0, min(growth_pct or 0.0, 200.0)) / 200.0  # normalize to 0-1, cap at 200% growth

    if competitor_count <= 1:
        competition: Literal["low", "medium", "high"] = "low"
        competition_score = 1.0
    elif competitor_count <= 4:
        competition = "medium"
        competition_score = 0.6
    else:
        competition = "high"
        competition_score = 0.25

    market_score = round(min(1.0, growth * 0.6 + competition_score * 0.4), 2)

    if market_score >= 0.7:
        priority: Literal["low", "medium", "high"] = "high"
    elif market_score >= 0.4:
        priority = "medium"
    else:
        priority = "low"

    return {"market_score": market_score, "competition": competition, "priority": priority}


def rank_trends(trends: list[dict], top_n: int = 10) -> list[dict]:
    """Sort trend dicts (each with a 'growth_pct' and 'confidence') by an
    impact score — growth weighted by how confident we are in it, so a
    huge but shaky number doesn't outrank a smaller, well-evidenced one."""
    def _impact(t: dict) -> float:
        growth = t.get("growth_pct") or 0.0
        confidence = t.get("confidence", 0.5)
        return growth * confidence

    return sorted(trends, key=_impact, reverse=True)[:top_n]