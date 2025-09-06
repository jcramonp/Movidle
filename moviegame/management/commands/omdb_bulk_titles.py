from django.core.management.base import BaseCommand, CommandError
import csv, time
from moviegame.services.omdb import OMDbClient, mapear_a_pelicula_dict, OMDbError
from moviegame.models import Pelicula

class Command(BaseCommand):
    help = "Carga/actualiza múltiples películas desde un CSV con columnas 'title,year'."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Ruta al CSV (utf-8) con columnas title,year (year opcional)")
        parser.add_argument("--sleep", type=float, default=0.8, help="Delay entre requests (evita rate limit)")

    def handle(self, *args, **opts):
        path = opts["file"]
        delay = max(0.2, float(opts["sleep"]))
        client = OMDbClient()
        ok = fail = 0
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                if "title" not in reader.fieldnames:
                    raise CommandError("El CSV debe tener al menos la columna 'title'.")
                for row in reader:
                    title = (row.get("title") or "").strip()
                    year_str = (row.get("year") or "").strip()
                    year = int(year_str) if year_str.isdigit() else None
                    if not title:
                        continue
                    try:
                        data = client.buscar_por_titulo(title, year)
                        payload = mapear_a_pelicula_dict(data)
                        # Evitamos duplicados por imdb_id si lo tenemos
                        if payload.get("imdb_id"):
                            Pelicula.objects.update_or_create(
                                imdb_id=payload["imdb_id"], defaults=payload
                            )
                        else:
                            Pelicula.objects.update_or_create(
                                titulo=payload["titulo"], anio=payload["anio"], defaults=payload
                            )
                        ok += 1
                        self.stdout.write(self.style.SUCCESS(f"✓ {payload['titulo']} ({payload['anio']})"))
                    except (OMDbError, Exception) as e:
                        fail += 1
                        self.stdout.write(self.style.ERROR(f"✗ {title} {year or ''}: {e}"))
                    time.sleep(delay)
        except FileNotFoundError:
            raise CommandError("No se pudo abrir el CSV.")

        self.stdout.write(self.style.WARNING(f"Listo. OK={ok} | Fallos={fail}"))
