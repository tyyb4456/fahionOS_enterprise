"""
meta-mcp — FashionOS MCP Server
Exposes the Meta Graph API (Instagram Business + Meta Ads) as MCP tools for
the Marketing Agent (and any future agent that needs paid-social or
Instagram data). Shares the same Redis credential cache as shopify-mcp
(fashionos:creds:{brand_id}) — the main API already writes
meta_access_token / meta_ad_account_id / instagram_access_token /
instagram_page_id into that exact key (see db/credentials.py,
api/routers/oauth.py::_sync_creds), so no new caching path is needed here.

Read tools  : get_instagram_account_insights, list_recent_instagram_media,
              get_instagram_media_insights, get_ad_account_summary,
              list_ad_campaigns
Write tools : publish_instagram_post, create_ad_campaign,
              update_campaign_budget, pause_campaign, resume_campaign

Note: Instagram/Meta Graph API metric names and endpoints move around
between API versions more than Shopify's — worth checking the exact
`metric=` list against current Meta docs if a read tool starts erroring.
"""

import logging
import os
import httpx
from datetime import datetime, timezone
from typing import Optional
from fastmcp import FastMCP
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# ── Multi-tenant credential fetching — same Redis key shopify-mcp reads ────

import redis.asyncio as _aioredis

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


async def _get_brand_creds(brand_id: str) -> dict:
    """
    Fetch decrypted brand credentials from Redis. Same cache key as
    shopify-mcp — the main API writes both Shopify and Meta credentials
    into the same fashionos:creds:{brand_id} blob.
    Raises ValueError if brand_id is not found in cache.
    """
    r = _aioredis.from_url(_REDIS_URL, decode_responses=True)
    try:
        raw = await r.get(f"fashionos:creds:{brand_id}")
        if not raw:
            logger.error("No Meta credentials found for brand_id=%s", brand_id)
            raise ValueError(
                f"No credentials found for brand_id='{brand_id}'. "
                "Ensure the brand exists and has connected Meta via OAuth."
            )
        import json as _json
        return _json.loads(raw)
    finally:
        await r.aclose()


# ── FastMCP app ───────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="meta-mcp",
    instructions=(
        "You have access to a brand's Meta Ads account and Instagram Business "
        "account. Use these tools to read engagement/ad performance and to "
        "publish content or manage ad campaigns. All write actions are logged. "
        "Ad spend changes are real money — double-check budgets before setting them."
    ),
)

GRAPH_VERSION = os.getenv("META_GRAPH_API_VERSION", "v21.0")
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


async def _graph_get(path: str, access_token: str, params: Optional[dict] = None) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{GRAPH_URL}/{path}", params={**(params or {}), "access_token": access_token})
        r.raise_for_status()
        return r.json()


async def _graph_post(path: str, access_token: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{GRAPH_URL}/{path}", data={**payload, "access_token": access_token})
        r.raise_for_status()
        return r.json()


# ── INSTAGRAM — READ ─────────────────────────────────────────────────────────

@mcp.tool()
async def get_instagram_account_insights(brand_id: str, period: str = "day", days: int = 7) -> dict:
    """
    Get account-level Instagram insights (reach, profile views, engaged
    accounts) for the connected Instagram Business account.

    Args:
        brand_id: The ID of the brand to query.
        period: "day" | "week" | "days_28".
        days: How many days of daily data points to request (default 7).

    Used by: Marketing Agent (campaign performance context, "what's working").
    """
    try:
        creds = await _get_brand_creds(brand_id)
    except ValueError as e:
        logger.error("Meta credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    ig_user_id = creds.get("instagram_page_id")
    token = creds.get("instagram_access_token")
    if not ig_user_id or not token:
        return {"error": "Instagram not connected for this brand."}

    since = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    try:
        data = await _graph_get(
            f"{ig_user_id}/insights",
            token,
            {
                "metric": "reach,profile_views,accounts_engaged",
                "period": period,
                "since": since,
                "until": int(datetime.now(timezone.utc).timestamp()),
            },
        )
    except httpx.HTTPStatusError as e:
        logger.error("Meta API HTTP error: %s", e.response.text)
        return {"error": f"Instagram insights request failed: {e.response.text}"}

    return {
        "period": period,
        "metrics": [
            {
                "name": m.get("name"),
                "values": [{"end_time": v.get("end_time"), "value": v.get("value")} for v in m.get("values", [])],
            }
            for m in data.get("data", [])
        ],
    }


@mcp.tool()
async def list_recent_instagram_media(brand_id: str, limit: int = 10) -> list[dict]:
    """
    List the account's most recent Instagram posts/reels with basic
    engagement counts.

    Args:
        brand_id: The ID of the brand to query.
        limit: Max items to return (default 10).

    Used by: Marketing Agent (avoid repeating a recent post, learn what's landing).
    """
    try:
        creds = await _get_brand_creds(brand_id)
    except ValueError as e:
        return [{"error": str(e)}]

    ig_user_id = creds.get("instagram_page_id")
    token = creds.get("instagram_access_token")
    if not ig_user_id or not token:
        return [{"error": "Instagram not connected for this brand."}]

    try:
        data = await _graph_get(
            f"{ig_user_id}/media", token,
            {"fields": "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count", "limit": limit},
        )
    except httpx.HTTPStatusError as e:
        logger.error("Meta API HTTP error: %s", e.response.text)
        return [{"error": f"Instagram media request failed: {e.response.text}"}]

    return [
        {
            "media_id": m.get("id"),
            "caption": m.get("caption", ""),
            "media_type": m.get("media_type"),
            "media_url": m.get("media_url"),
            "permalink": m.get("permalink"),
            "timestamp": m.get("timestamp"),
            "like_count": m.get("like_count", 0),
            "comments_count": m.get("comments_count", 0),
        }
        for m in data.get("data", [])
    ]


@mcp.tool()
async def get_instagram_media_insights(brand_id: str, media_id: str) -> dict:
    """
    Get engagement insights (impressions, reach, saves, engagement) for one
    published Instagram post.

    Args:
        brand_id: The ID of the brand to query.
        media_id: The Instagram media ID (from list_recent_instagram_media
                  or the id returned by publish_instagram_post).

    Used by: Marketing Agent (content_performance tracking).
    """
    try:
        creds = await _get_brand_creds(brand_id)
    except ValueError as e:
        logger.error("Meta credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    token = creds.get("instagram_access_token")
    if not token:
        return {"error": "Instagram not connected for this brand."}

    try:
        data = await _graph_get(f"{media_id}/insights", token, {"metric": "impressions,reach,saved,engagement"})
    except httpx.HTTPStatusError as e:
        logger.error("Meta API HTTP error: %s", e.response.text)
        return {"error": f"Media insights request failed: {e.response.text}"}

    return {m.get("name"): (m.get("values", [{}])[0] or {}).get("value") for m in data.get("data", [])}


# ── INSTAGRAM — WRITE ────────────────────────────────────────────────────────

@mcp.tool()
async def publish_instagram_post(brand_id: str, image_url: str, caption: str) -> dict:
    """
    Publish a single-image Instagram feed post.

    Args:
        brand_id:  The ID of the brand to query.
        image_url: Publicly reachable URL of the image to post (e.g. a
                   product image from Shopify's list_products/get_product_by_sku).
        caption:   Post caption, including hashtags.

    Two-step Instagram Content Publishing flow: create a media container,
    then publish it. Returns the published media_id and permalink.
    Used by: Marketing Agent (content execution).
    """
    try:
        creds = await _get_brand_creds(brand_id)
    except ValueError as e:
        logger.error("Meta credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    ig_user_id = creds.get("instagram_page_id")
    token = creds.get("instagram_access_token")
    if not ig_user_id or not token:
        return {"error": "Instagram not connected for this brand."}

    try:
        container = await _graph_post(f"{ig_user_id}/media", token, {"image_url": image_url, "caption": caption})
        creation_id = container.get("id")
        if not creation_id:
            return {"error": f"Failed to create media container: {container}"}

        published = await _graph_post(f"{ig_user_id}/media_publish", token, {"creation_id": creation_id})
        media_id = published.get("id")
        if not media_id:
            return {"error": f"Failed to publish media container {creation_id}: {published}"}

        permalink_data = await _graph_get(f"{media_id}", token, {"fields": "permalink"})
    except httpx.HTTPStatusError as e:
        logger.error("Meta API HTTP error: %s", e.response.text)
        return {"error": f"Instagram publish failed: {e.response.text}"}

    return {
        "success": True,
        "media_id": media_id,
        "permalink": permalink_data.get("permalink"),
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


# ── META ADS — READ ──────────────────────────────────────────────────────────

@mcp.tool()
async def get_ad_account_summary(brand_id: str, date_preset: str = "last_7d") -> dict:
    """
    Get spend/performance summary for the brand's Meta Ads account.

    Args:
        brand_id: The ID of the brand to query.
        date_preset: Meta's date_preset values, e.g. "today", "yesterday",
                     "last_7d", "last_30d".

    Returns spend, impressions, clicks, CTR, CPC, and purchase actions if tracked.
    Used by: Marketing Agent (should we scale, hold, or cut ad spend).
    """
    try:
        creds = await _get_brand_creds(brand_id)
    except ValueError as e:
        logger.error("Meta credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    ad_account_id = creds.get("meta_ad_account_id")
    token = creds.get("meta_access_token")
    if not ad_account_id or not token:
        return {"error": "Meta Ads not connected for this brand."}

    try:
        data = await _graph_get(
            f"{ad_account_id}/insights", token,
            {"fields": "spend,impressions,clicks,ctr,cpc,actions", "date_preset": date_preset},
        )
    except httpx.HTTPStatusError as e:
        logger.error("Meta API HTTP error: %s", e.response.text)
        return {"error": f"Ad account insights request failed: {e.response.text}"}

    rows = data.get("data", [])
    if not rows:
        return {"date_preset": date_preset, "spend": 0.0, "impressions": 0, "clicks": 0, "message": "No ad activity in this window."}

    row = rows[0]
    purchases = next((a.get("value") for a in row.get("actions", []) if a.get("action_type") == "purchase"), None)
    return {
        "date_preset": date_preset,
        "spend": float(row.get("spend", 0)),
        "impressions": int(row.get("impressions", 0)),
        "clicks": int(row.get("clicks", 0)),
        "ctr": float(row.get("ctr", 0)),
        "cpc": float(row.get("cpc", 0)) if row.get("cpc") else None,
        "purchases": int(purchases) if purchases else None,
    }


@mcp.tool()
async def list_ad_campaigns(brand_id: str, status_filter: Optional[str] = None) -> list[dict]:
    """
    List Meta Ads campaigns on the brand's ad account.

    Args:
        brand_id: The ID of the brand to query.
        status_filter: Optional — "ACTIVE" | "PAUSED" | "ARCHIVED" | "DELETED".
                       Omit to return all.

    Used by: Marketing Agent, before deciding whether to launch a new
    campaign or adjust an existing one.
    """
    try:
        creds = await _get_brand_creds(brand_id)
    except ValueError as e:
        return [{"error": str(e)}]

    ad_account_id = creds.get("meta_ad_account_id")
    token = creds.get("meta_access_token")
    if not ad_account_id or not token:
        return [{"error": "Meta Ads not connected for this brand."}]

    params = {"fields": "id,name,status,objective,daily_budget,lifetime_budget,created_time"}
    if status_filter:
        params["filtering"] = f'[{{"field":"campaign.status","operator":"IN","value":["{status_filter}"]}}]'

    try:
        data = await _graph_get(f"{ad_account_id}/campaigns", token, params)
    except httpx.HTTPStatusError as e:
        logger.error("Meta API HTTP error: %s", e.response.text)
        return [{"error": f"Campaign list request failed: {e.response.text}"}]

    return [
        {
            "campaign_id": c.get("id"),
            "name": c.get("name"),
            "status": c.get("status"),
            "objective": c.get("objective"),
            "daily_budget": c.get("daily_budget"),
            "lifetime_budget": c.get("lifetime_budget"),
            "created_time": c.get("created_time"),
        }
        for c in data.get("data", [])
    ]


# ── META ADS — WRITE ──────────────────────────────────────────────────────────

@mcp.tool()
async def create_ad_campaign(
    brand_id: str,
    name: str,
    objective: str,
    daily_budget: float,
    status: str = "PAUSED",
    reason: str = "",
) -> dict:
    """
    Create a new Meta Ads campaign.

    Args:
        brand_id:     The ID of the brand to query.
        name:         Campaign name.
        objective:    Meta campaign objective, e.g. "OUTCOME_TRAFFIC",
                      "OUTCOME_SALES", "OUTCOME_ENGAGEMENT", "OUTCOME_AWARENESS".
        daily_budget: Daily budget in plain currency units (e.g. 25.0 for
                      $25/day) — this tool converts to Meta's expected
                      minor-unit integer internally.
        status:       "PAUSED" (default — recommended until targeting/
                      creative are verified) or "ACTIVE" to launch immediately.
        reason:       Why this campaign is being created — stored in audit log.

    This creates a real campaign shell — ad sets/creative still need to be
    built via follow-up Graph API calls before it can actually serve.
    Returns the campaign_id.
    Used by: Marketing Agent (campaign execution).
    """
    try:
        creds = await _get_brand_creds(brand_id)
    except ValueError as e:
        logger.error("Meta credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    ad_account_id = creds.get("meta_ad_account_id")
    token = creds.get("meta_access_token")
    if not ad_account_id or not token:
        return {"error": "Meta Ads not connected for this brand."}

    payload = {
        "name": name,
        "objective": objective,
        "status": status,
        "daily_budget": int(round(daily_budget * 100)),  # Meta expects minor units (cents)
        "special_ad_categories": "[]",
    }
    try:
        result = await _graph_post(f"{ad_account_id}/campaigns", token, payload)
    except httpx.HTTPStatusError as e:
        logger.error("Meta API HTTP error: %s", e.response.text)
        return {"error": f"Meta rejected the campaign: {e.response.text}"}

    return {
        "success": True,
        "campaign_id": result.get("id"),
        "name": name,
        "status": status,
        "daily_budget": daily_budget,
        "reason": reason,
    }


@mcp.tool()
async def update_campaign_budget(brand_id: str, campaign_id: str, daily_budget: float, reason: str = "") -> dict:
    """
    Change a campaign's daily budget.

    Args:
        brand_id:     The ID of the brand to query.
        campaign_id:  Meta campaign ID (from list_ad_campaigns or create_ad_campaign).
        daily_budget: New daily budget in plain currency units (e.g. 30.0 for $30/day).
        reason:       Why the budget is changing — stored in audit log.

    Real money — only call this after checking get_ad_account_summary shows
    the spend is justified.
    Used by: Marketing Agent (scale winners, cut underperformers).
    """
    try:
        creds = await _get_brand_creds(brand_id)
    except ValueError as e:
        logger.error("Meta credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    token = creds.get("meta_access_token")
    if not token:
        return {"error": "Meta Ads not connected for this brand."}

    try:
        await _graph_post(campaign_id, token, {"daily_budget": int(round(daily_budget * 100))})
    except httpx.HTTPStatusError as e:
        logger.error("Meta API HTTP error: %s", e.response.text)
        return {"error": f"Budget update failed: {e.response.text}"}

    return {"success": True, "campaign_id": campaign_id, "new_daily_budget": daily_budget, "reason": reason}


@mcp.tool()
async def pause_campaign(brand_id: str, campaign_id: str, reason: str = "") -> dict:
    """
    Pause a running Meta Ads campaign.

    Args:
        brand_id:    The ID of the brand to query.
        campaign_id: Meta campaign ID.
        reason:      Why it's being paused — stored in audit log.

    Used by: Marketing Agent (cut spend on an underperforming or
    out-of-stock-triggered campaign immediately).
    """
    return await _set_campaign_status(brand_id, campaign_id, "PAUSED", reason)


@mcp.tool()
async def resume_campaign(brand_id: str, campaign_id: str, reason: str = "") -> dict:
    """
    Resume a paused Meta Ads campaign.

    Args:
        brand_id:    The ID of the brand to query.
        campaign_id: Meta campaign ID.
        reason:      Why it's being resumed — stored in audit log.
    """
    return await _set_campaign_status(brand_id, campaign_id, "ACTIVE", reason)


async def _set_campaign_status(brand_id: str, campaign_id: str, status: str, reason: str) -> dict:
    """Internal helper (not an @mcp.tool() itself — pause/resume_campaign
    delegate to this rather than calling each other's decorated tool
    functions directly)."""
    try:
        creds = await _get_brand_creds(brand_id)
    except ValueError as e:
        logger.error("Meta credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    token = creds.get("meta_access_token")
    if not token:
        return {"error": "Meta Ads not connected for this brand."}

    try:
        await _graph_post(campaign_id, token, {"status": status})
    except httpx.HTTPStatusError as e:
        logger.error("Meta API HTTP error: %s", e.response.text)
        return {"error": f"Status update failed: {e.response.text}"}

    return {"success": True, "campaign_id": campaign_id, "status": status, "reason": reason}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8002)