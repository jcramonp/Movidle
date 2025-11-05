

export DJANGO_SETTINGS_MODULE=movidle.settings

set -e
set -x  # <- más logs

python --version
echo "DEBUG=$DEBUG"
echo "ALLOWED_HOSTS=$ALLOWED_HOSTS"
echo "DATABASE_URL present? $( [ -n "$DATABASE_URL" ] && echo yes || echo no )"

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Crear/actualizar superusuario (idempotente)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
python - <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "movidle.settings")
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

username = os.environ["DJANGO_SUPERUSER_USERNAME"]
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
password = os.environ["DJANGO_SUPERUSER_PASSWORD"]

u, created = User.objects.get_or_create(username=username, defaults={"email": email})
u.is_superuser = True
u.is_staff = True
u.set_password(password)   # fuerza/actualiza la contraseña
u.save()
print("Superuser", "created" if created else "updated")
PY
fi


# Logs a stdout/stderr y puerto 8000
exec gunicorn movidle.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
