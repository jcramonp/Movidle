import io, csv
from typing import Iterable
from .interfaces import ReportGenerator

class CsvReportGenerator(ReportGenerator):
    content_type = "text/csv"
    extension = "csv"

    def generate(self, peliculas: Iterable) -> bytes:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "titulo", "anio", "genero"])
        for p in peliculas:
            w.writerow([getattr(p, "id", ""), getattr(p, "titulo", ""),
                        getattr(p, "anio", ""), getattr(p, "genero", "")])
        # UTF-8 con BOM para que Excel lo reconozca bien
        return ("\ufeff" + buf.getvalue()).encode("utf-8")
