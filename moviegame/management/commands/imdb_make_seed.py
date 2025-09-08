# moviegame/management/commands/imdb_make_seed.py
from django.core.management.base import BaseCommand
from django.db import transaction
import csv
import gzip
import io
import sys
import urllib.request
from pathlib import Path

"""
Genera seed_movies.csv con las 1000 películas más votadas en IMDb (proxy de popularidad).
Fuente oficial (datasets actualizados a diario):
- https://datasets.imdbws.com/title.ratings.tsv.gz
- https://datasets.imdbws.com/title.basics.tsv.gz

Criterios:
- titleType == "movie"
- isAdult == "0"
- Orden: numVotes desc
- Campos de salida: title,year

Uso:
  python manage.py imdb_make_seed --top 1000 --out seed_movies.csv

Opciones:
  --top N            (por defecto 1000)
  --out RUTA         (por defecto "seed_movies.csv" en el cwd)
  --oversample K     (toma los K tconst con más votos y luego filtra por 'movie'; default 200000)
"""

RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
BASICS_URL  = "https://datasets.imdbws.com/title.basics.tsv.gz"


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def _read_tsv_gz(buf: bytes):
    # Devuelve un iterador de filas (dict) desde un .tsv.gz en memoria
    bio = io.BytesIO(buf)
    with gzip.open(bio, mode="rt", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            yield row


class Command(BaseCommand):
    help = "Construye seed_movies.csv con las películas más votadas en IMDb (non-commercial datasets)."

    def add_arguments(self, parser):
        parser.add_argument("--top", type=int, default=1000, help="Cantidad de títulos (default 1000)")
        parser.add_argument("--out", type=str, default="seed_movies.csv", help="Ruta de salida CSV")
        parser.add_argument(
            "--oversample",
            type=int,
            default=200_000,
            help="Cuántos tconst top por votos considerar antes de filtrar por 'movie' (default 200k)",
        )

    def handle(self, *args, **opts):
        top_n = int(opts["top"])
        out_path = Path(opts["out"])
        oversample = int(opts["oversample"])

        self.stdout.write(self.style.NOTICE("Descargando ratings..."))
        ratings_buf = _download(RATINGS_URL)

        # 1) Tomar los más votados (tconst, numVotes)
        self.stdout.write(self.style.NOTICE("Procesando ratings (ordenando por numVotes desc)..."))
        votes = []
        for r in _read_tsv_gz(ratings_buf):
            tconst = r.get("tconst")
            nv = r.get("numVotes")
            if not tconst or not nv or nv == "\\N":
                continue
            try:
                num_votes = int(nv)
            except ValueError:
                continue
            votes.append((tconst, num_votes))

        # Orden descendente por votos y nos quedamos con un gran "oversample"
        votes.sort(key=lambda x: x[1], reverse=True)
        top_pool = {t for (t, _) in votes[:oversample]}
        del votes  # liberar memoria

        # 2) Leer basics y filtrar solo películas adult==0 con tconst en top_pool
        self.stdout.write(self.style.NOTICE("Descargando basics..."))
        basics_buf = _download(BASICS_URL)

        self.stdout.write(self.style.NOTICE("Filtrando 'movie' no adult y armando TOP..."))
        results = []
        for b in _read_tsv_gz(basics_buf):
            tconst = b.get("tconst")
            if tconst not in top_pool:
                continue
            if b.get("titleType") != "movie":
                continue
            if b.get("isAdult") not in ("0", 0, None):
                continue

            title = b.get("primaryTitle") or b.get("originalTitle") or ""
            year = b.get("startYear")
            if not title:
                continue
            if not year or year == "\\N":
                continue
            try:
                year_int = int(year)
            except ValueError:
                continue

            results.append((title, year_int))
            if len(results) >= top_n:
                break

        if not results:
            self.stderr.write(self.style.ERROR("No se obtuvieron resultados. ¿Problemas de red o formato?"))
            sys.exit(1)

        # 3) Escribir CSV: title,year
        self.stdout.write(self.style.NOTICE(f"Escribiendo CSV ({len(results)} filas) → {out_path}"))
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["title", "year"])
            for title, year in results:
                w.writerow([title, year])

        self.stdout.write(self.style.SUCCESS(f"Listo: {out_path.resolve()}"))
        self.stdout.write(self.style.SUCCESS("Ahora puedes cargar a tu BD con omdb_bulk_titles."))
