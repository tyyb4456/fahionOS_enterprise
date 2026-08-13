"""
Lightweight, dependency-light deterministic helpers for the Customer
Support Agent — return/exchange eligibility windows, refund math, an
escalation guardrail, and recurring-issue detection from ticket history.
Same philosophy as agents/inventory/forecasting.py, agents/finance/
analytics.py, etc.: good enough to unblock the agent today, not a
replacement for a real returns-management platform.

Eligibility WINDOWS themselves (how many days, restocking fees, who pays
return shipping) are brand policy and come from retrieve_policy (RAG),
not from here — this module only does the date/amount arithmetic once
the agent already has the policy's numbers in hand.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def days_since(reference: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    if reference is None:
        return None
    now = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return (now - reference).days


def check_window_eligibility(delivered_at: Optional[datetime], window_days: int, now: Optional[datetime] = None) -> dict:
    """
    Pure date math for a return/exchange/cancellation window — `window_days`
    is the brand's actual policy number (get it from retrieve_policy first,
    don't guess it). Returns whether the order is still inside the window
    and how many days remain/elapsed.
    """
    elapsed = days_since(delivered_at, now=now)
    if elapsed is None:
        return {"eligible": None, "days_elapsed": None, "days_remaining": None, "reason": "No delivery date on file — can't determine eligibility."}

    eligible = elapsed <= window_days
    return {
        "eligible": eligible,
        "days_elapsed": elapsed,
        "days_remaining": max(0, window_days - elapsed),
        "reason": (
            f"{elapsed} days since delivery, within the {window_days}-day window."
            if eligible else
            f"{elapsed} days since delivery — outside the {window_days}-day window."
        ),
    }


def calculate_refund_amount(
    line_item_price: float,
    quantity: int,
    restocking_fee_pct: float = 0.0,
    deduct_original_shipping: bool = False,
    original_shipping_cost: float = 0.0,
) -> dict:
    """
    Deterministic refund math — restocking_fee_pct and whether shipping is
    deducted are brand policy (from retrieve_policy), the arithmetic
    itself shouldn't be left to the LLM.
    """
    gross = round(line_item_price * quantity, 2)
    restocking_fee = round(gross * (restocking_fee_pct / 100.0), 2)
    shipping_deduction = round(original_shipping_cost, 2) if deduct_original_shipping else 0.0
    net = round(max(0.0, gross - restocking_fee - shipping_deduction), 2)
    return {
        "gross_amount": gross,
        "restocking_fee": restocking_fee,
        "shipping_deduction": shipping_deduction,
        "net_refund_amount": net,
    }


def should_auto_escalate(
    priority: str,
    sentiment: str,
    previous_open_issues: int,
    refund_amount: Optional[float] = None,
    refund_auto_approval_limit: float = 20000.0,
) -> dict:
    """
    Deterministic escalation guardrail the agent's own judgment sits on
    top of — mirrors Finance's evaluate_purchase_order safety-floor
    pattern. Any one of these trips it: critical priority, a refund past
    the auto-approval limit, or a customer with a track record of repeat
    unresolved issues plus negative sentiment (churn risk).
    """
    reasons = []
    if priority == "critical":
        reasons.append("Ticket flagged critical priority.")
    if refund_amount is not None and refund_amount > refund_auto_approval_limit:
        reasons.append(f"Refund amount {refund_amount} exceeds the auto-approval limit of {refund_auto_approval_limit}.")
    if previous_open_issues >= 2 and sentiment == "negative":
        reasons.append(f"Customer has {previous_open_issues} prior unresolved issues and current sentiment is negative — churn risk.")

    return {"escalate": bool(reasons), "reasons": reasons}


def detect_recurring_issue(tickets: list[dict], min_occurrences: int = 3) -> list[dict]:
    """
    Groups recent tickets by issue_type to surface the "32% of returns for
    Hoodie X are caused by sizing confusion" kind of pattern — the raw
    counting only; the agent still decides whether it's worth a
    flag_recurring_issue write and what to say about it.
    """
    counts: dict[str, int] = {}
    for t in tickets:
        key = t.get("issue_type", "other")
        counts[key] = counts.get(key, 0) + 1

    total = len(tickets) or 1
    return [
        {"issue_type": issue_type, "count": count, "share_pct": round(count / total * 100, 1)}
        for issue_type, count in sorted(counts.items(), key=lambda kv: -kv[1])
        if count >= min_occurrences
    ]