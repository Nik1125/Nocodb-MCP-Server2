FROM python:3.12-slim

# рабочая директория
WORKDIR /app

# зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# код
COPY . .

# Railway пробрасывает порт в $PORT
ENV HOST=0.0.0.0
ENV PORT=${PORT}

# экспонируем порт (Railway сам подставит $PORT)
EXPOSE ${PORT}

# запуск сервера
CMD ["python", "nocodb_mcp_server.py", "--transport", "http", "--host", "0.0.0.0", "--port", "${PORT}"]
