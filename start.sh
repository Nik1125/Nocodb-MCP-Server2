#!/usr/bin/env sh
set -eu

PORT_TO_USE="${PORT:-8000}"
echo "Resolved PORT=${PORT_TO_USE}"
echo "Starting fastmcp on 0.0.0.0:${PORT_TO_USE}"

# ЯВНО указываем путь к файлу .py
exec fastmcp run ./nocodb_mcp_server.py \
  --transport http \
  --host 0.0.0.0 \
  --port "${PORT_TO_USE}"
