#!/usr/bin/env bash
set -e

# Migraciones y estáticos
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Crear superusuario automático si pasas variables (ver Paso 3)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py createsuperuser --noinput || true
fi

# Arrancar gunicorn
exec gunicorn movidle.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 60
