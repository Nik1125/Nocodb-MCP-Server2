#!/usr/bin/env sh
set -eu

PORT_TO_USE="${PORT:-8000}"
echo "Resolved PORT=${PORT_TO_USE}"
echo "Starting fastmcp (module import) on 0.0.0.0:${PORT_TO_USE}"

# важно: указываем, что это модуль, и даём PYTHONPATH=.
export PYTHONPATH="/app:${PYTHONPATH:-}"

exec fastmcp run --as-module nocodb_mcp_server:mcp \
  --transport http \
  --host 0.0.0.0 \
  --port "${PORT_TO_USE}"
