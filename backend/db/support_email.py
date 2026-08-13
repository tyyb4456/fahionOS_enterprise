"""
Generates each brand's dedicated inbound support-email alias.

One shared FashionOS-controlled domain (Resend Inbound configured once,
platform-wide — see api/routers/customer_support_webhook.py) with brand
routing done via plus-addressing, e.g.
support+brand_xxxxx@support.fashionos.app — no per-brand Resend/DNS
config needed, consistent with how outbound email already uses a single
FashionOS-managed sending identity (RESEND_FROM_EMAIL) rather than a
per-brand one.
"""
import os

INBOUND_EMAIL_DOMAIN = os.getenv("INBOUND_EMAIL_DOMAIN", "support.fashionos.app")


def generate_support_inbound_email(brand_id: str) -> str:
    return f"support+{brand_id}@{INBOUND_EMAIL_DOMAIN}"