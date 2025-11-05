# moviegame/tests.py
from django.test import TestCase
from django.urls import reverse
from moviegame.models import Pelicula

class PeliculaModelTest(TestCase):
    def test_str_y_helpers_basicos(self):
        peli = Pelicula.objects.create(
            titulo="Aliens",
            anio=1986,
            genero="Action, Sci-Fi, Horror",
            actores="Sigourney Weaver, Michael Biehn, Bill Paxton",
            director="James Cameron",
            duracion_min=137,
            imdb_rating=8.4,
            imdb_votes=750000,
        )
        self.assertEqual(str(peli), "Aliens (1986)")
        self.assertEqual(peli.lista_generos(), ["Action", "Sci-Fi", "Horror"])
        self.assertEqual(
            peli.lista_actores(), ["Sigourney Weaver", "Michael Biehn", "Bill Paxton"]
        )

class PublicMoviesAPITest(TestCase):
    def test_api_public_movies_responde_ok_y_estructura_basica(self):
        Pelicula.objects.create(
            titulo="Alien",
            anio=1979,
            genero="Horror, Sci-Fi",
            director="Ridley Scott",
            actores="Sigourney Weaver, Tom Skerritt",
            imdb_rating=8.5,
            imdb_votes=900000,
            duracion_min=117,
        )
        Pelicula.objects.create(
            titulo="Blade Runner",
            anio=1982,
            genero="Sci-Fi, Thriller",
            director="Ridley Scott",
            actores="Harrison Ford, Rutger Hauer",
            imdb_rating=8.1,
            imdb_votes=800000,
            duracion_min=117,
        )

        url = reverse("moviegame:api_public_movies")
        resp = self.client.get(url, {"limit": 2})
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertEqual(data.get("provider"), "Movidle")
        self.assertIn("results", data)
        self.assertEqual(data.get("count"), len(data.get("results")))
        for item in data["results"]:
            for key in ("id", "title", "year", "genres", "runtime_min",
                        "imdb_rating", "popularity_votes", "app_url"):
                self.assertIn(key, item)
