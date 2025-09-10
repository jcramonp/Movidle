from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from moviegame.services.omdb import OMDbClient, mapear_a_pelicula_dict, OMDbError
from moviegame.models import Pelicula


class Command(BaseCommand):
    help = "Añade/actualiza una película desde OMDb (por título/año o imdbID)."

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group(required=True)
        g.add_argument("--title", help="Título exacto (OMDb 't=')")
        g.add_argument("--imdb", help="imdbID (p.ej. tt0133093)")
        parser.add_argument("--year", type=int, help="Año (opcional con --title)")

    @transaction.atomic
    def handle(self, *args, **opts):
        client = OMDbClient()
        try:
            if opts["imdb"]:
                data = client.buscar_por_imdb_id(opts["imdb"])
            else:
                data = client.buscar_por_titulo(opts["title"], opts.get("year"))
        except OMDbError as e:
            raise CommandError(str(e))

        payload = mapear_a_pelicula_dict(data)
        titulo = payload.get("titulo")
        anio = payload.get("anio")
        imdb_id = payload.get("imdb_id")

        if not titulo or not anio:
            raise CommandError("OMDb no devolvió datos suficientes (titulo/anio).")

        obj = None

        # 1) Si viene imdb_id, intenta por imdb_id
        if imdb_id:
            obj = Pelicula.objects.filter(imdb_id=imdb_id).first()

        # 2) Si no existe por imdb_id, intenta por (titulo, anio) (case-insensitive)
        if obj is None:
            obj = Pelicula.objects.filter(titulo__iexact=titulo, anio=anio).first()

        # 3) Actualiza o crea
        if obj:
            for k, v in payload.items():
                setattr(obj, k, v)
            obj.save()
            self.stdout.write(self.style.WARNING(f"ACTUALIZADA: {obj}"))
        else:
            obj = Pelicula.objects.create(**payload)
            self.stdout.write(self.style.SUCCESS(f"CREADA: {obj}"))
