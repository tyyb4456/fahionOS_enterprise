# ─────────────────────────────────────────────────────────────────────────────
# supplier-mcp — FashionOS MCP Server
# Exposes simulated external procurement data (marketplace supplier search,
# courier shipment tracking) as MCP tools to the Supplier Agent.
#
# Build:  docker build -t fashionos/supplier-mcp .
# Run:    docker run -p 8003:8003 fashionos/supplier-mcp
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

EXPOSE 8003

CMD ["python", "server.py"]