#!/usr/bin/env sh
set -euo pipefail

PORT_TO_USE="${PORT:-8080}"
echo "Resolved PORT=${PORT_TO_USE}"
echo "Starting FastMCP on 0.0.0.0:${PORT_TO_USE}"

# БЫЛО (неправильно): nocodb_mcp_server:app
# СТАЛО (правильно):   nocodb_mcp_server.py:app  ← обязательно с .py
exec fastmcp run ./nocodb_mcp_server.py \
  --transport http \
  --host 0.0.0.0 \
  --port "${PORT_TO_USE}"
