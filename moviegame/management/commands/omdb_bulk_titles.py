from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import csv, time

from moviegame.services.omdb import OMDbClient, mapear_a_pelicula_dict, OMDbError
from moviegame.models import Pelicula


class Command(BaseCommand):
    help = (
        "Carga/actualiza películas desde un CSV con columnas 'title,year'. "
        "Usa OMDb para poblar (imdb_id, votos, rating, duración, géneros, etc.)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Ruta al CSV UTF-8 con columnas title,year")
        parser.add_argument("--sleep", type=float, default=0.8, help="Delay entre requests (seg.)")
        parser.add_argument("--start", type=int, default=0, help="Índice inicial (0-based) para reanudar")
        parser.add_argument("--limit", type=int, default=0, help="Máximo de filas a procesar (0 = todas)")
        parser.add_argument("--only-missing", dest="only_missing", action="store_true",
                            help="Solo procesar títulos que aún no existen por imdb_id o (titulo,año)")
        parser.add_argument("--require-fields", dest="require_fields", action="store_true",
                            help="Descartar resultados sin imdbVotes/rating/duration (no se importan).")

    def handle(self, *args, **opts):
        path = opts["file"]
        delay = max(0.2, float(opts["sleep"]))
        start = max(0, int(opts["start"]))
        limit = max(0, int(opts["limit"]))
        only_missing = bool(opts.get("only_missing", False))      # <-- nombres con underscore
        require_fields = bool(opts.get("require_fields", False))  # <--

        client = OMDbClient()
        ok = fail = skip = 0

        try:
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                if "title" not in reader.fieldnames:
                    raise CommandError("El CSV debe tener columna 'title'.")
                rows = list(reader)
        except FileNotFoundError:
            raise CommandError(f"No se encontró el archivo: {path}")

        # Slicing por start/limit (para reanudar o cargar por partes)
        if start or limit:
            end = start + limit if limit else None
            rows = rows[start:end]

        total = len(rows)
        self.stdout.write(self.style.NOTICE(f"Procesando {total} filas (delay {delay}s) ..."))

        for row in rows:
            title = (row.get("title") or "").strip()
            year_str = (row.get("year") or "").strip()
            year = int(year_str) if year_str.isdigit() else None

            if not title:
                skip += 1
                continue

            try:
                if only_missing:
                    exists = Pelicula.objects.filter(titulo__iexact=title, anio=year or 0).exists()
                    if exists:
                        skip += 1
                        continue

                data = client.buscar_por_titulo(title, year)
                payload = mapear_a_pelicula_dict(data)

                if require_fields:
                    if not (payload.get("imdb_votes") and payload.get("imdb_rating") and payload.get("duracion_min")):
                        skip += 1
                        self.stdout.write(self.style.WARNING(f"- skip (faltan campos): {title} {year or ''}"))
                        time.sleep(delay)
                        continue

                with transaction.atomic():
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
            finally:
                time.sleep(delay)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"OK = {ok}"))
        self.stdout.write(self.style.WARNING(f"SKIP = {skip}"))
        self.stdout.write(self.style.ERROR(f"FAIL = {fail}"))
        self.stdout.write(self.style.NOTICE("Listo."))
