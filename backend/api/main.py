"""
FashionOS — FastAPI Application
================================
Session 9: Research Agent router mounted.
"""

import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from logging_config import setup_logging
setup_logging()

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import brands, clerk_webhook, oauth, chat, shopify_webhook, policy_documents, office, customer_support_webhook, courier, dashboard, approvals
from api.routers.webchat import webchat_app
from api.routers.agents import (
    inventory as inventory_agent,
    sales as sales_agent,
    marketing as marketing_agent,
    finance as finance_agent,
    research as research_agent,
    supplier as supplier_agent,
    customer_support as customer_support_agent,
    product as product_agent,
)

import sys
sys.dont_write_bytecode = True

APP_VERSION = "0.3.0"
BRAND_NAME  = os.getenv("BRAND_NAME", "FashionOS Brand")
REDIS_URL   = os.getenv("REDIS_URL", "redis://localhost:6379/0")



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Redis check
    try:
        r = aioredis.from_url(REDIS_URL, socket_connect_timeout=3)
        await r.ping()
        await r.aclose()
        print(f"[FashionOS] ✓ Redis connected")
    except Exception as e:
        print(f"[FashionOS] △ Redis not reachable: {e}")

    # Warm the deep-agent Redis singletons (store + checkpointer) at boot.
    # AsyncRedisStore.setup() / AsyncRedisSaver.asetup() create search
    # indices the first time they run — doing that here means the first
    # person to open /chat after a deploy doesn't personally eat that cost.
    try:
        from deep_agent.runtime import get_store, get_checkpointer
        await asyncio.gather(get_store(), get_checkpointer())
        print("[FashionOS] ✓ Deep agent Redis store + checkpointer warmed")
    except Exception as e:
        print(f"[FashionOS] △ Deep agent Redis warmup failed (will retry lazily): {e}")


    yield
    print("[FashionOS] Shutting down API.")


app = FastAPI(
    title       = f"FashionOS API — {BRAND_NAME}",
    description = (
        "Autonomous multi-agent fashion brand OS. "
        "Receives Shopify webhooks, triggers agent pipelines, "
        "exposes run history, approval queues, and dashboard data."
    ),
    version  = APP_VERSION,
    lifespan = lifespan,
)


CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins     = CORS_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


app.include_router(brands.router)
app.include_router(clerk_webhook.router)
app.include_router(oauth.router)
app.include_router(courier.router)
app.include_router(chat.router)

# Previously missing — Shopify webhooks registered in api/routers/oauth.py
# point at shopify_webhook.router's routes, so without this mounted, every
# webhook Shopify sends 404s and the Postgres mirror never syncs.
app.include_router(shopify_webhook.router)
app.include_router(policy_documents.router)
app.include_router(office.router)
app.include_router(customer_support_webhook.router)
app.include_router(dashboard.router)
app.include_router(approvals.router)
app.include_router(inventory_agent.router)
app.include_router(sales_agent.router)
app.include_router(marketing_agent.router)
app.include_router(finance_agent.router)
app.include_router(research_agent.router)
app.include_router(supplier_agent.router)
app.include_router(customer_support_agent.router)
app.include_router(product_agent.router)

# Isolated sub-app with its own permissive CORS — see api/routers/webchat.py
app.mount("/api/v1/support/webchat", webchat_app)


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/v1/status", tags=["ops"])
async def system_status():
    redis_ok = False
    try:
        r = aioredis.from_url(REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        redis_ok = True
    except Exception:
        pass

    return {
        "status":  "ok" if redis_ok else "degraded",
        "version": APP_VERSION,
        "brand":   BRAND_NAME,

        "redis":   "connected" if redis_ok else "unreachable",

        "agents": {
            "inventory": "active",
            "sales":     "active",
            "marketing": "active",
            "finance":   "active",
            "research":  "active",
            "supplier":  "active",
            "customer_support": "active",
            "product":   "active",
        },
    }