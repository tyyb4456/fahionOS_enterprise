"""
Lightweight, dependency-light analytics for the Marketing Agent — audience
scoring, best-posting-time, and hashtag suggestion. Same philosophy as
agents/inventory/forecasting.py and agents/sales/analytics.py: good enough
to unblock the agent today without a dedicated trend/SEO model, and kept
deterministic on purpose — anything that can be computed from data the
agent already has shouldn't be left to the LLM to eyeball (the same
reasoning the other two agents' system prompts already spell out for their
own tools, e.g. "Use forecast_sku_demand rather than eyeballing velocity
trends yourself").

Actual copywriting (captions/emails/SMS) is deliberately NOT here — that's
inherently generative and lives in agents/marketing/tools.py as a
dedicated creative-LLM call instead.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np

# ── Audience scoring ──────────────────────────────────────────────────────

_SEGMENT_GOAL_AFFINITY = {
    # segment -> goal keywords it tends to respond well to
    "VIP":      ["early access", "exclusive", "loyalty", "vip", "premium", "launch"],
    "Loyal":    ["repeat", "loyalty", "restock", "new arrival", "bundle"],
    "New":      ["welcome", "awareness", "introduce", "discovery", "first order"],
    "At Risk":  ["win back", "win-back", "we miss you", "discount", "re-engage"],
    "Inactive": ["win back", "win-back", "reactivate", "discount", "comeback"],
}


def score_audiences(goal: str, segments: list[dict]) -> list[dict]:
    """
    Rank a brand's existing customer segments (from Sales Agent's
    CustomerSegment table) against a campaign goal, using keyword affinity
    plus segment size as a tiebreaker. Falls back to a generic
    "general audience" recommendation when there's no segment data yet.
    """
    goal_lower = (goal or "").lower()
    if not segments:
        return [{
            "segment": "General audience",
            "rationale": "No customer segments on file yet — target broadly and let "
                         "get_customer_segments narrow this down once Sales Agent has run.",
            "estimated_size": None,
        }]

    scored = []
    for s in segments:
        name = s.get("segment", "")
        keywords = _SEGMENT_GOAL_AFFINITY.get(name, [])
        hits = sum(1 for kw in keywords if kw in goal_lower)
        score = hits * 10 + min(s.get("customer_count", 0), 1000) / 1000  # size as a small tiebreaker
        scored.append((score, s))

    scored.sort(key=lambda t: -t[0])
    top = [s for _, s in scored[:3] if s.get("customer_count", 0) > 0]
    if not top:
        top = [scored[0][1]]

    return [
        {
            "segment": s.get("segment", ""),
            "rationale": s.get("definition", "") or f"Best available match for: {goal}",
            "estimated_size": s.get("customer_count"),
        }
        for s in top
    ]


# ── Best posting time ─────────────────────────────────────────────────────

_DEFAULT_POSTING_TIMES = {
    "instagram": {"day_of_week": "Wednesday", "hour_local": 12, "note": "No history yet — using general Instagram engagement defaults."},
    "facebook":  {"day_of_week": "Thursday",  "hour_local": 13, "note": "No history yet — using general Facebook engagement defaults."},
    "tiktok":    {"day_of_week": "Tuesday",   "hour_local": 19, "note": "No history yet — using general TikTok engagement defaults."},
    "email":     {"day_of_week": "Tuesday",   "hour_local": 10, "note": "No history yet — using general email open-rate defaults."},
    "sms":       {"day_of_week": "Friday",    "hour_local": 11, "note": "No history yet — using general SMS response-rate defaults."},
}


def best_posting_time(platform: str, performance_history: list[dict]) -> dict:
    """
    Looks at this brand's own ContentPerformance history for the platform
    and returns the day/hour with the highest average engagement. Falls
    back to a sane platform default when there isn't enough history yet
    (needs at least 5 data points before trusting an actual pattern).
    """
    platform = platform.lower()
    relevant = [h for h in performance_history if h.get("platform", "").lower() == platform and h.get("recorded_at")]

    if len(relevant) < 5:
        default = _DEFAULT_POSTING_TIMES.get(platform, _DEFAULT_POSTING_TIMES["instagram"])
        return {"platform": platform, **default, "sample_size": len(relevant)}

    buckets: dict[tuple[str, int], list[float]] = {}
    for h in relevant:
        dt = datetime.fromisoformat(h["recorded_at"])
        key = (dt.strftime("%A"), dt.hour)
        buckets.setdefault(key, []).append(float(h.get("engagement", 0)))

    best_key, best_scores = max(buckets.items(), key=lambda kv: float(np.mean(kv[1])))
    return {
        "platform": platform,
        "day_of_week": best_key[0],
        "hour_local": best_key[1],
        "note": f"Based on {len(relevant)} of this brand's own posts.",
        "sample_size": len(relevant),
    }


# ── Hashtags ──────────────────────────────────────────────────────────────

_EVERGREEN_FASHION_TAGS = {
    "instagram": ["ootd", "fashion", "style", "newarrival", "shopnow"],
    "tiktok":    ["fashiontok", "styleinspo", "ootd", "fashionfinds"],
    "facebook":  ["fashion", "style", "newcollection"],
}


def suggest_hashtags(topic: str, platform: str, product_tags: Optional[list[str]] = None, count: int = 8) -> list[str]:
    """
    Deterministic hashtag suggestion — normalizes the topic + any Shopify
    product tags into hashtag form, then rounds out the set with
    evergreen, platform-appropriate fashion tags. Not a trend model; if you
    need what's trending *right now*, that's a live-data tool, not this.
    """
    platform = platform.lower()
    words = []
    for source in ([topic] + list(product_tags or [])):
        for token in str(source).replace("/", " ").replace("-", " ").split():
            clean = "".join(ch for ch in token if ch.isalnum())
            if clean and len(clean) > 2:
                words.append(clean.lower())

    seen: list[str] = []
    for w in words:
        tag = f"#{w}"
        if tag not in seen:
            seen.append(tag)

    for tag in _EVERGREEN_FASHION_TAGS.get(platform, _EVERGREEN_FASHION_TAGS["instagram"]):
        full = f"#{tag}"
        if full not in seen:
            seen.append(full)
        if len(seen) >= count:
            break

    return seen[:count]
