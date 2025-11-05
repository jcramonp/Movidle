# Dockerfile
FROM python:3.11-slim

ENV DJANGO_SETTINGS_MODULE=movidle.settings \
    PYTHONPATH=/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# deps del sistema para psycopg2 y Pillow (por si tu app usa imágenes)
RUN apt-get update && apt-get install -y \
    build-essential libpq-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app

# script de arranque
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
CMD ["/entrypoint.sh"]
