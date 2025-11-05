#!/usr/bin/env bash
set -euo pipefail
set -x

# Info útil en logs
python --version
echo "DEBUG=${DEBUG:-}"
echo "ALLOWED_HOSTS=${ALLOWED_HOSTS:-}"
echo "DATABASE_URL present? $( [ -n "${DATABASE_URL:-}" ] && echo yes || echo no )"

# Migraciones y estáticos
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Crear/actualizar superusuario de forma idempotente usando manage.py (Django ya cargado)
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
User = get_user_model()
u, created = User.objects.get_or_create(
    username=os.environ['DJANGO_SUPERUSER_USERNAME'],
    defaults={'email': os.environ.get('DJANGO_SUPERUSER_EMAIL','')}
)
u.is_superuser = True
u.is_staff = True
u.set_password(os.environ['DJANGO_SUPERUSER_PASSWORD'])
u.save()
print('Superuser', 'created' if created else 'updated')
"
fi

# Iniciar Gunicorn en el puerto 8000
exec gunicorn movidle.wsgi:application \
  --chdir /app \
  --env DJANGO_SETTINGS_MODULE=movidle.settings \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
