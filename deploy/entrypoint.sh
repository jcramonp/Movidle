#!/usr/bin/env bash
set -e
set -x  # <- más logs

python --version
echo "DEBUG=$DEBUG"
echo "ALLOWED_HOSTS=$ALLOWED_HOSTS"
echo "DATABASE_URL present? $( [ -n "$DATABASE_URL" ] && echo yes || echo no )"

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py createsuperuser --noinput || true
fi

# Logs a stdout/stderr y puerto 8000
exec gunicorn movidle.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
