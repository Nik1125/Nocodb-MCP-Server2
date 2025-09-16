# serve.py
import os
from nocodb_mcp_server import mcp

host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("PORT", "8000"))

print(f"Serving MCP HTTP on {host}:{port}")

# Запускаем HTTP-сервер FastMCP напрямую
# (в разных версиях API метод может называться по-разному — оставляем fallback)
try:
    mcp.run_http(host=host, port=port)
except AttributeError:
    mcp.run(transport="http", host=host, port=port)
