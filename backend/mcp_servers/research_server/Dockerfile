# ─────────────────────────────────────────────────────────────────────────────
# research-mcp — FashionOS MCP Server
# Exposes public market-intelligence tools (search, trends, page fetching)
# to the Research Agent.
#
# Build:  docker build -t fashionos/research-mcp .
# Run:    docker run --env-file .env -p 8003:8003 fashionos/research-mcp
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