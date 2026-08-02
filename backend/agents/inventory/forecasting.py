"""
Lightweight forecasting for the Inventory Agent.

This is intentionally a simple, dependency-light model (weighted moving
average + linear trend) rather than Prophet/XGBoost/LightGBM — good enough
to unblock the agent today. Swap the internals of `forecast_sku_demand` for
a real model later; its signature and return shape are the contract the
rest of the system (tools.py, output_schema.py) depends on, not the model
itself. This mirrors the design doc's `forecast_sales(product_id)` — "the
LLM decides *when* to use the tool, the tool performs the prediction."
"""
from __future__ import annotations

import numpy as np


def forecast_sku_demand(
    current_stock: float,
    daily_sales_history: list[float],
    forecast_days: int = 30,
    safety_stock_days: int = 3,
) -> dict:
    """
    Args:
        current_stock: units currently available.
        daily_sales_history: units sold per day, oldest first (e.g. last 14-30 days).
        forecast_days: horizon to project forward.
        safety_stock_days: buffer used to compute a recommended reorder point.

    Returns predicted daily/period demand, projected days until stockout,
    a rough confidence score, and a trend label.
    """
    history = [max(0.0, float(x)) for x in daily_sales_history]

    if not history:
        return {
            "predicted_units_per_day": 0.0,
            "predicted_units_sold": 0.0,
            "predicted_stock_remaining": current_stock,
            "days_until_stockout": None,
            "confidence": 0.1,
            "trend": "unknown",
            "recommended_reorder_point": 0.0,
        }

    n = len(history)
    # recent days weigh up to 2x older days
    weights = np.linspace(1.0, 2.0, num=n)
    weighted_avg = float(np.average(history, weights=weights))

    trend = "stable"
    slope = 0.0
    if n >= 4:
        x = np.arange(n)
        slope, _intercept = np.polyfit(x, history, 1)
        if slope > 0.05 * (weighted_avg + 1e-6):
            trend = "increasing"
        elif slope < -0.05 * (weighted_avg + 1e-6):
            trend = "decreasing"

    projected_daily = max(0.0, float(weighted_avg + slope * (forecast_days / 2)))
    predicted_units_sold = float(round(projected_daily * forecast_days, 1))
    # clamp at 0 — stock can't go negative; once demand outpaces stock the
    # meaningful number is days_until_stockout, not a deficit count
    predicted_stock_remaining = float(round(max(0.0, current_stock - predicted_units_sold), 1))

    days_until_stockout = (
        float(round(current_stock / projected_daily, 1)) if projected_daily > 0 else None
    )

    variance = float(np.var(history)) if n > 1 else 0.0
    mean = weighted_avg or 1e-6
    coefficient_of_variation = (variance ** 0.5) / mean
    confidence = max(
        0.2,
        min(0.97, 1.0 - min(coefficient_of_variation, 1.0) * 0.6 - (0.15 if n < 7 else 0.0)),
    )

    recommended_reorder_point = float(round(projected_daily * safety_stock_days, 1))

    return {
        "predicted_units_per_day": float(round(projected_daily, 2)),
        "predicted_units_sold": predicted_units_sold,
        "predicted_stock_remaining": predicted_stock_remaining,
        "days_until_stockout": days_until_stockout,
        "confidence": float(round(confidence, 2)),
        "trend": trend,
        "recommended_reorder_point": recommended_reorder_point,
    }
