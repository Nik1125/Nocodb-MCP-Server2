#!/usr/bin/env sh
set -eu

# Railway сам выставляет $PORT. Печатаем для контроля.
echo "Resolved PORT=${PORT:-<empty>}"

PORT_TO_USE="${PORT:-8000}"   # fallback 8000 для локального запуска
echo "Starting NocoDB MCP on 0.0.0.0:${PORT_TO_USE}"

# Запускаем сервер
exec python nocodb_mcp_server.py \
  --transport http \
  --host 0.0.0.0 \
  --port "${PORT_TO_USE}"
