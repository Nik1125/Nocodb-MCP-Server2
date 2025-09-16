#!/usr/bin/env sh
set -eu

PORT_TO_USE="${PORT:-8000}"
echo "Resolved PORT=${PORT_TO_USE}"
echo "Starting fastmcp (python -m) on 0.0.0.0:${PORT_TO_USE}"

# 1-й вариант: модульная форма (рекомендуется)
exec python -m fastmcp.run nocodb_mcp_server:mcp \
  --transport http \
  --host 0.0.0.0 \
  --port "${PORT_TO_USE}"

# Если вдруг у тебя очень старый fastmcp и эта команда не взлетит,
# вернись и раскомментируй запасной вариант ниже:
# exec fastmcp run nocodb_mcp_server:mcp \
#   --transport http \
#   --host 0.0.0.0 \
#   --port "${PORT_TO_USE}"
