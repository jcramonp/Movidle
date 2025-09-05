# created by Valentina
from django.core.management.base import BaseCommand
from django.utils import timezone
from moviegame.services.game_service import seleccionar_pelicula_diaria

class Command(BaseCommand):
    help = "Muestra la película secreta del día (según la selección determinística)."

    def handle(self, *args, **opts):
        hoy = timezone.localdate()
        peli = seleccionar_pelicula_diaria(hoy)
        self.stdout.write(self.style.SUCCESS(f"{hoy} → {peli.titulo} ({peli.anio})"))
