# Real MCP server (spec 03 T8; compose service `mcp`, build context = repo root):
#   docker build -f apps/mcp/Dockerfile .
# Serves http://0.0.0.0:8001/mcp behind X-API-Key, one uvicorn worker. Needs MCP_API_KEY, DATABASE_URL and gold mounted
# read-only at GOLD_PATH (spec 06 FR-09). infra/compose.dev.yml overrides the command to run the fixture server
# `mcp_server.fake` (no key, no gold): local only, never deployed (spec 03 AC-06).
FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastmcp>=4.0,<5" "pydantic>=2.7,<3" "uvicorn>=0.30,<1" "duckdb>=1.1" \
    "psycopg[binary]>=3.2,<4" "pyyaml>=6" "jsonschema>=4" tzdata \
 && useradd --system --no-create-home mcp
COPY packages/ packages/
COPY contracts/ contracts/
COPY apps/mcp/ apps/mcp/
ENV PYTHONPATH=/app:/app/packages:/app/apps/mcp PYTHONUNBUFFERED=1 GOLD_PATH=/gold/v1
USER mcp
EXPOSE 8001
CMD ["python", "-m", "mcp_server", "--host", "0.0.0.0", "--port", "8001"]
