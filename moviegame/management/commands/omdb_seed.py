# created by Valentina
from __future__ import annotations
import time
from typing import Iterable
from django.core.management.base import BaseCommand
from moviegame.services.omdb import OMDbClient, mapear_a_pelicula_dict, OMDbError
from moviegame.models import Pelicula

"""
Formato del archivo:
- Una película por línea.
- Puedes usar:  "Titulo;Año"  o  "imdbID" (tt.....)
Ej:
The Matrix;1999
Inception;2010
tt6751668
"""


def parse_line(line: str) -> tuple[str, int] | tuple[str, None]:
    line = line.strip()
    if not line or line.startswith("#"):
        return ("", None)
    if line.startswith("tt"):  # imdbID directo
        return (line, None)
    if ";" in line:
        t, y = line.split(";", 1)
        y = y.strip()
        return (t.strip(), int(y) if y.isdigit() else None)
    return (line, None)


class Command(BaseCommand):
    help = "Importa múltiples películas desde un archivo (una por línea)."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Ruta del archivo de títulos")
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Segundos entre requests (respeta el rate-limit de OMDb)",
        )

    def handle(self, *args, **opts):
        path = opts["file"]
        delay = max(0.2, opts["sleep"])
        client = OMDbClient()

        total, creadas, act, fallos = 0, 0, 0, 0
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                titulo, year_or_none = parse_line(raw)
                if not titulo:
                    continue
                total += 1
                try:
                    if titulo.startswith("tt"):
                        data = client.buscar_por_imdb_id(titulo)
                    else:
                        data = client.buscar_por_titulo(titulo, year_or_none)
                    payload = mapear_a_pelicula_dict(data)

                    if payload.get("imdb_id"):
                        obj, created = Pelicula.objects.update_or_create(
                            imdb_id=payload["imdb_id"], defaults=payload
                        )
                    else:
                        obj, created = Pelicula.objects.update_or_create(
                            titulo=payload["titulo"],
                            anio=payload["anio"],
                            defaults=payload,
                        )
                    if created:
                        creadas += 1
                        self.stdout.write(self.style.SUCCESS(f"+ {obj}"))
                    else:
                        act += 1
                        self.stdout.write(self.style.WARNING(f"~ {obj}"))
                except (OMDbError, Exception) as e:
                    fallos += 1
                    self.stdout.write(self.style.ERROR(f"! {titulo}: {e}"))
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. Total líneas: {total} | Creadas: {creadas} | Actualizadas: {act} | Fallos: {fallos}"
            )
        )
