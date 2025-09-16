#!/usr/bin/env sh
set -euo pipefail

PORT_TO_USE="${PORT:-8080}"
echo "Resolved PORT=${PORT_TO_USE}"
echo "Starting FastMCP on 0.0.0.0:${PORT_TO_USE}"

exec fastmcp run nocodb_mcp_server:app \
  --transport http \
  --host 0.0.0.0 \
  --port "${PORT_TO_USE}"
