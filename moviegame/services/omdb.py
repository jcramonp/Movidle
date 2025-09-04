# moviegame/services/omdb.py
from __future__ import annotations
import requests
from django.conf import settings

BASE_URL = "https://www.omdbapi.com/"

class OMDbError(RuntimeError):
    pass

class OMDbClient:
    def __init__(self, api_key: str | None = None, timeout: int = 10):
        self.api_key = api_key or getattr(settings, "OMDB_API_KEY", "")
        if not self.api_key:
            raise OMDbError("Falta OMDB_API_KEY en settings/.env")
        self.timeout = timeout

    def _get(self, params: dict) -> dict:
        params = {"apikey": self.api_key, **params}
        r = requests.get(BASE_URL, params=params, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if data.get("Response") == "False":
            # OMDb devuelve "Response: False" y un "Error"
            raise OMDbError(data.get("Error", "OMDb devolvió Response=False"))
        return data

    def buscar_por_titulo(self, titulo: str, year: int | None = None) -> dict:
        params = {"t": titulo.strip(), "type": "movie"}
        if year:
            params["y"] = str(year)
        return self._get(params)

    def buscar_por_imdb_id(self, imdb_id: str) -> dict:
        return self._get({"i": imdb_id.strip()})

def _int_year(value: str | None) -> int:
    if not value:
        return 0
    # OMDb a veces envía "2010–" o rangos
    return int(str(value).split("–")[0] or 0)

def mapear_a_pelicula_dict(omdb_json: dict) -> dict:
    """Convierte JSON de OMDb al dict compatible con el modelo Pelicula."""
    def safe(x: str | None) -> str:
        return "" if (x is None or x == "N/A") else x
    return {
        "titulo": safe(omdb_json.get("Title")).strip(),
        "anio": _int_year(omdb_json.get("Year")),
        "genero": safe(omdb_json.get("Genre")),
        "director": safe(omdb_json.get("Director")),
        "actores": safe(omdb_json.get("Actors")),
        "imdb_id": safe(omdb_json.get("imdbID")) or None,
        "poster_url": safe(omdb_json.get("Poster")),
    }
