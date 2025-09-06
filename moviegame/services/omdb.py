# moviegame/services/omdb.py
from __future__ import annotations

from decimal import Decimal
import requests
from django.conf import settings

BASE_URL = "https://www.omdbapi.com/"

class OMDbError(RuntimeError):
    """Error de cliente OMDb."""

class OMDbClient:
    """
    Cliente mínimo para OMDb.
    Usa la API key configurada en settings.OMDB_API_KEY (o .env).
    """
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
        """
        Busca una película exacta por título (y opcionalmente año).
        """
        params = {"t": titulo.strip(), "type": "movie"}
        if year:
            params["y"] = str(year)
        return self._get(params)

    def buscar_por_imdb_id(self, imdb_id: str) -> dict:
        """Trae una película por IMDb ID (p.ej. 'tt1375666')."""
        return self._get({"i": imdb_id.strip()})

# -----------------------
# Helpers de parseo
# -----------------------

def _int_year(value: str | None) -> int:
    """
    OMDb a veces envía '2010–' o rangos; nos quedamos con el primer número.
    """
    if not value or value == "N/A":
        return 0
    try:
        return int(str(value).split("–")[0].split("-")[0])
    except Exception:
        return 0

def _parse_runtime_min(value: str | None) -> int:
    """
    OMDb 'Runtime': '136 min' o 'N/A' -> 136 o 0.
    """
    if not value or value == "N/A":
        return 0
    try:
        return int(str(value).split()[0])
    except Exception:
        return 0

def _parse_int(value: str | None) -> int | None:
    """
    Convierte '1,234,567' -> 1234567. Devuelve None si N/A.
    """
    if not value or value == "N/A":
        return None
    try:
        return int(str(value).replace(",", ""))
    except Exception:
        return None

def _parse_decimal(value: str | None) -> Decimal | None:
    """
    Convierte '8.7' -> Decimal('8.7'). Devuelve None si N/A.
    """
    if not value or value == "N/A":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None

# -----------------------
# Mapeo a nuestro modelo
# -----------------------

def mapear_a_pelicula_dict(omdb_json: dict) -> dict:
    """
    Convierte JSON de OMDb al diccionario compatible con el modelo Pelicula.
    NO guarda en BD; el caller decide crear/actualizar.

    Campos mapeados:
    - titulo, anio ("año"), genero, director, actores
    - imdb_id, poster_url
    - duracion_min, imdb_rating, imdb_votes
    """
    def safe(x: str | None) -> str:
        return "" if (x is None or x == "N/A") else x

    return {
        "titulo": safe(omdb_json.get("Title")).strip(),
        "anio": _int_year(omdb_json.get("Year")),                 # etiqueta visible "año" en el modelo
        "genero": safe(omdb_json.get("Genre")),
        "director": safe(omdb_json.get("Director")),
        "actores": safe(omdb_json.get("Actors")),
        "imdb_id": (safe(omdb_json.get("imdbID")) or None),
        "poster_url": safe(omdb_json.get("Poster")),

        # Nuevos atributos para el juego:
        "duracion_min": _parse_runtime_min(omdb_json.get("Runtime")),
        "imdb_rating": _parse_decimal(omdb_json.get("imdbRating")),  # Decimal(0.0..10.0)
        "imdb_votes": _parse_int(omdb_json.get("imdbVotes")),        # int
    }
