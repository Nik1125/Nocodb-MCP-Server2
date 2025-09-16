#!/usr/bin/env sh
set -eu

PORT_TO_USE="${PORT:-8000}"
echo "Resolved PORT=${PORT_TO_USE}"
echo "Starting fastmcp (module import) on 0.0.0.0:${PORT_TO_USE}"

# ВАЖНО: импортируем как МОДУЛЬ, а не путь к файлу
exec python -m mcp.server.fastmcp.cli run nocodb_mcp_server:mcp \
  --transport http \
  --host 0.0.0.0 \
  --port "${PORT_TO_USE}"
