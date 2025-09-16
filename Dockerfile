FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir fastmcp

COPY . .

# Railway сам задаёт $PORT
ENV PORT=8000
EXPOSE 8000

# ВАЖНО: запускаем сервер в режиме HTTP (Streamable HTTP)
CMD ["fastmcp","run","nocodb_mcp_server.py","--transport","http","--host","0.0.0.0","--port","${PORT}"]
