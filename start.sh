#!/usr/bin/env sh
set -eu

PORT_TO_USE="${PORT:-8000}"
echo "Resolved PORT=${PORT_TO_USE}"
echo "Starting serve.py on 0.0.0.0:${PORT_TO_USE}"

exec python /app/serve.py
