import io
from typing import Iterable
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from .interfaces import ReportGenerator

class PdfReportGenerator(ReportGenerator):
    content_type = "application/pdf"
    extension = "pdf"

    def generate(self, peliculas: Iterable) -> bytes:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4

        y = height - 2*cm
        c.setFont("Helvetica-Bold", 12)
        c.drawString(2*cm, y, "Reporte de Películas")
        y -= 1*cm
        c.setFont("Helvetica", 10)

        # Evitamos PDFs gigantes; ajusta si quieres
        for idx, p in enumerate(peliculas):
            line = f"{getattr(p, 'id', '')} - {getattr(p, 'titulo', '')} ({getattr(p, 'anio', '')}) [{getattr(p, 'genero', '')}]"
            c.drawString(2*cm, y, line[:110])
            y -= 0.6*cm
            if y < 2*cm:
                c.showPage()
                y = height - 2*cm
                c.setFont("Helvetica", 10)
            if idx > 2000:  # tope de seguridad
                break

        c.save()
        return buf.getvalue()
