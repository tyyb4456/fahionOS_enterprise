# ─────────────────────────────────────────────────────────────────────────────
# customer-support-mcp — FashionOS MCP Server
# Exposes simulated courier delivery-status tracking to the Customer
# Support Agent.
#
# Build:  docker build -t fashionos/customer-support-mcp .
# Run:    docker run -p 8005:8005 fashionos/customer-support-mcp
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install \
    --default-timeout=300 \
    -r requirements.txt

COPY server.py .

EXPOSE 8005

CMD ["python", "server.py"]