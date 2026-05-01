FROM python:3.10-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY . .

RUN uv sync

ENTRYPOINT ["uv", "run", "mcp-routing-gateway", "--work-dir", ".", "--config", "gateway_config.json", "--mcp-config", "mcp_config.sample.json"]