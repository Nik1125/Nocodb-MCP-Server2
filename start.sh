#!/usr/bin/env sh
set -euo pipefail

PORT_TO_USE="${PORT:-8080}"
echo "Resolved PORT=${PORT_TO_USE}"
echo "Starting MCP (official) on 0.0.0.0:${PORT_TO_USE}"

# ВАЖНО: запускаем сам скрипт, без `mcp run`
exec python ./nocodb_mcp_server.py
