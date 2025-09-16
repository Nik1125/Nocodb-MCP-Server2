FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONUNBUFFERED=1

# В shell-форме переменные окружения подставляются
CMD sh -c 'python nocodb_mcp_server.py --transport http --host 0.0.0.0 --port ${PORT:-8000}'
