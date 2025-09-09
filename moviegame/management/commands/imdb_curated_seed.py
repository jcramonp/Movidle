from django.core.management.base import BaseCommand
import csv
import gzip
import io
import sys
import urllib.request
from collections import defaultdict, Counter
from pathlib import Path

"""
Genera un seed CSV (title,year) equilibrado con 1000 películas conocidas:
- Fuente: datasets públicos de IMDb (basics + ratings)
- Filtros:
  * titleType = movie
  * isAdult = 0
  * year entre --year-min y --year-max
  * rating mínimo (--rating-min)
  * umbral de votos por década (más bajo para décadas antiguas)
- Balance:
  * Cuotas por década (reparto flexible)
  * Tope por género ("primario": primer género en basics.genres) por década

Uso típico:
  python manage.py imdb_curated_seed --top 1000 --out seed_movies.csv

Luego cargas con:
  python manage.py omdb_bulk_titles --file seed_movies.csv --sleep 1.2 --only-missing
"""

RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
BASICS_URL  = "https://datasets.imdbws.com/title.basics.tsv.gz"

DEFAULT_DECADE_VOTE_MIN = {
    # Umbral mínimo (aprox.) de votos por década: más bajo en décadas antiguas
    1930:  8000,
    1940: 12000,
    1950: 20000,
    1960: 30000,
    1970: 40000,
    1980: 50000,
    1990: 70000,
    2000: 80000,
    2010: 100000,
    2020: 60000,  # menor por "menos tiempo en cartel"
}

DEFAULT_DECADE_TARGETS = {
    # Reparto orientativo (suma 500). Se ajusta dinámicamente si faltan candidatos.
    1970:  40,
    1980:  50,
    1990:  50,
    2000: 140,
    2010: 120,
    2020: 100,
}

PRIMARY_GENRE_CAP_FRACTION = 0.28  # máx. ~28% del cupo de una década por el mismo "primer" género
DEFAULT_MIN_RATING = 7.0


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def _read_tsv_gz(buf: bytes):
    bio = io.BytesIO(buf)
    with gzip.open(bio, mode="rt", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            yield row


def _decade(year: int) -> int:
    return (year // 10) * 10


class Command(BaseCommand):
    help = "Genera un CSV curado (title,year) equilibrado por décadas y géneros a partir de datasets IMDb."

    def add_arguments(self, parser):
        parser.add_argument("--top", type=int, default=1000, help="Cantidad destino (default 1000)")
        parser.add_argument("--out", type=str, default="seed_movies.csv", help="Ruta salida CSV")
        parser.add_argument("--year-min", type=int, default=1950, help="Año mínimo (default 1950)")
        parser.add_argument("--year-max", type=int, default=2025, help="Año máximo (default 2025)")
        parser.add_argument("--rating-min", type=float, default=DEFAULT_MIN_RATING, help="Rating mínimo IMDb")
        parser.add_argument("--strict", action="store_true",
                            help="Si una década no llena su cupo, NO redistribuye (deja menos de 'top').")
        parser.add_argument("--print-stats", action="store_true", help="Muestra resumen por década/género.")

    def handle(self, *args, **opts):
        top_n = int(opts["top"])
        out_path = Path(opts["out"])
        year_min = int(opts["year_min"])
        year_max = int(opts["year_max"])
        rating_min = float(opts["rating_min"])
        strict = bool(opts["strict"])
        show_stats = bool(opts["print_stats"])

        self.stdout.write(self.style.NOTICE("Descargando ratings IMDb..."))
        ratings_buf = _download(RATINGS_URL)

        # ratings: tconst -> (rating, numVotes)
        ratings = {}
        for r in _read_tsv_gz(ratings_buf):
            tconst = r.get("tconst")
            ar = r.get("averageRating")
            nv = r.get("numVotes")
            if not tconst or not ar or not nv or ar == "\\N" or nv == "\\N":
                continue
            try:
                ratings[tconst] = (float(ar), int(nv))
            except ValueError:
                continue

        self.stdout.write(self.style.NOTICE("Descargando basics IMDb..."))
        basics_buf = _download(BASICS_URL)

        # Candidatos por década
        buckets = defaultdict(list)  # decade -> list[dict]
        total_read = 0
        kept = 0

        for b in _read_tsv_gz(basics_buf):
            total_read += 1
            if b.get("titleType") != "movie":
                continue
            if b.get("isAdult") not in ("0", 0, None):
                continue

            year_s = b.get("startYear")
            if not year_s or year_s == "\\N":
                continue
            try:
                year = int(year_s)
            except ValueError:
                continue
            if year < year_min or year > year_max:
                continue

            tconst = b.get("tconst")
            if tconst not in ratings:
                continue

            rating, votes = ratings[tconst]
            if rating < rating_min:
                continue

            dec = _decade(year)
            # Umbral por década (si no existe, usa un valor razonable)
            vote_min = DEFAULT_DECADE_VOTE_MIN.get(dec, 50000)
            if votes < vote_min:
                continue

            title = b.get("primaryTitle") or b.get("originalTitle") or ""
            if not title:
                continue

            genres_s = b.get("genres") or ""
            genres = [g.strip() for g in genres_s.split(",") if g and g != "\\N"]
            primary_genre = genres[0] if genres else "Unknown"

            runtime_s = b.get("runtimeMinutes")
            runtime = None
            if runtime_s and runtime_s != "\\N":
                try:
                    runtime = int(runtime_s)
                except ValueError:
                    runtime = None

            buckets[dec].append({
                "tconst": tconst,
                "title": title,
                "year": year,
                "rating": rating,
                "votes": votes,
                "genres": genres,
                "pgenre": primary_genre,
                "runtime": runtime,
            })
            kept += 1

        if kept == 0:
            self.stderr.write(self.style.ERROR("No hay candidatos tras filtros. Ajusta rating/votes/year."))
            sys.exit(1)

        # Orden dentro de cada década: por votos desc, luego rating desc, luego título
        for dec in list(buckets.keys()):
            buckets[dec].sort(key=lambda x: (-x["votes"], -x["rating"], x["title"]))

        # Determinar décadas involucradas y cuotas destino
        decades = sorted(d for d in buckets.keys())
        targets = {}
        remaining = top_n

        # Base: usa DEFAULT_DECADE_TARGETS intersectado con decades disponibles
        base_total = sum(DEFAULT_DECADE_TARGETS.get(d, 0) for d in decades)
        if base_total == 0:
            # reparto proporcional a cantidad de candidatos por década
            total_candidates = sum(len(buckets[d]) for d in decades)
            for d in decades:
                frac = len(buckets[d]) / total_candidates
                take = round(frac * top_n)
                targets[d] = min(take, len(buckets[d]))
        else:
            # normaliza las cuotas a top_n y recorta si no hay tantos candidatos
            scale = top_n / base_total
            for d in decades:
                base = DEFAULT_DECADE_TARGETS.get(d, 0)
                take = round(base * scale)
                targets[d] = min(take, len(buckets[d]))

        # Si no llenamos por falta de candidatos y strict=False, redistribuye sobras
        picked_total = sum(targets.values())
        if picked_total < top_n and not strict:
            short = top_n - picked_total
            # Redistribuir a décadas con más stock
            stock = [(d, len(buckets[d]) - targets[d]) for d in decades]
            stock.sort(key=lambda x: x[1], reverse=True)
            i = 0
            while short > 0 and any(s > 0 for _, s in stock):
                d, s = stock[i % len(stock)]
                if s > 0:
                    targets[d] += 1
                    s -= 1
                    short -= 1
                    stock[i % len(stock)] = (d, s)
                i += 1

        # Selección aplicando tope por género dentro de cada década
        results = []
        genre_caps = {}
        for d in decades:
            cap = max(1, int(targets[d] * PRIMARY_GENRE_CAP_FRACTION))
            genre_caps[d] = cap

            taken = 0
            per_genre = Counter()
            for item in buckets[d]:
                if taken >= targets[d]:
                    break
                pg = item["pgenre"]
                if per_genre[pg] >= cap:
                    continue
                results.append((item["title"], item["year"], d, pg, item["votes"], item["rating"]))
                per_genre[pg] += 1
                taken += 1

            # Si no se alcanzó el target (por cap), rellena ignorando cap
            if taken < targets[d]:
                for item in buckets[d]:
                    if taken >= targets[d]:
                        break
                    if (item["title"], item["year"], d, item["pgenre"], item["votes"], item["rating"]) in results:
                        continue
                    results.append((item["title"], item["year"], d, item["pgenre"], item["votes"], item["rating"]))
                    taken += 1

        # Si aún sobra (estrict=False), rellena de cualquier década con stock
        if len(results) < top_n and not strict:
            need = top_n - len(results)
            pool = []
            for d in decades:
                pool.extend(buckets[d])
            # quitar los ya elegidos
            chosen = {(t, y) for (t, y, *_rest) in results}
            for item in pool:
                key = (item["title"], item["year"])
                if key in chosen:
                    continue
                results.append((item["title"], item["year"], _decade(item["year"]), item["pgenre"], item["votes"], item["rating"]))
                if len(results) >= top_n:
                    break

        # Volcado CSV
        results = results[:top_n]
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["title", "year"])
            for title, year, *_rest in results:
                w.writerow([title, year])

        # Stats opcionales
        if show_stats:
            by_dec = Counter(r[2] for r in results)
            by_g  = Counter(r[3] for r in results)
            self.stdout.write("---- RESUMEN ----")
            self.stdout.write("Por década:")
            for d in sorted(by_dec.keys()):
                self.stdout.write(f"  {d}s: {by_dec[d]}")
            self.stdout.write("Por género (primario):")
            for g, c in by_g.most_common():
                self.stdout.write(f"  {g}: {c}")

        self.stdout.write(self.style.SUCCESS(f"OK: escrito {out_path.resolve()} con {len(results)} títulos."))
        self.stdout.write(self.style.NOTICE("Ahora ejecuta: python manage.py omdb_bulk_titles --file seed_movies.csv --sleep 1.2 --only-missing"))
