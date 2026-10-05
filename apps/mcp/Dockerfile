# Fake MCP server for the local stack (spec 01 T4; compose service `mcp`, build context = repo root).
# Task 03d replaces it with the real server image. Serves http://0.0.0.0:8001/mcp. It has no API key: never deploy it
# publicly (spec 03 AC-06).
FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastmcp>=4.0,<5" "pydantic>=2.7,<3"
COPY packages/ packages/
COPY contracts/ contracts/
COPY apps/mcp/ apps/mcp/
ENV PYTHONPATH=/app:/app/packages:/app/apps/mcp PYTHONUNBUFFERED=1
EXPOSE 8001
CMD ["python", "-m", "mcp_server.fake", "--host", "0.0.0.0", "--port", "8001"]
