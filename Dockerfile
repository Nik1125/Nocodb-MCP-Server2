FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/start.sh

# Без EXPOSE и без ENV PORT — всё придёт от Railway
ENV PYTHONUNBUFFERED=1

CMD ["/app/start.sh"]
