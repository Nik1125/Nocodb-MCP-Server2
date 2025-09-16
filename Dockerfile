FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway положит PORT в окружение сам
ENV HOST=0.0.0.0

# В shell-форме переменные подставятся
CMD sh -c 'python nocodb_mcp_server.py --transport http --host 0.0.0.0 --port ${PORT}'
