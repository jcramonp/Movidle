from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import unicodedata

from django.db import transaction
from django.utils import timezone

from ..models import (
    Pelicula,
    Jugador,
    Partida,
    Intento,
    Feedback,
    PeliculaDelDia,
    ColorCategoria,
    EstadoPartida,
)

# =========================
# Config de reglas
# =========================
MAX_INTENTOS = 10
YEAR_DELTA = 5  # ±5 años -> AMARILLO
DUR_DELTA = 30  # ±30 min -> AMARILLO
VOTES_DELTA = 100_000  # ±100k votos -> AMARILLO
RATING_DELTA = 1.0  # ±1.0 -> AMARILLO


# =========================
# Resultado que devolvemos a la API
# =========================
@dataclass
class ResultadoIntento:
    intento_id: int
    numero_intento: int

    color_anio: str
    arrow_anio: str

    color_popularidad: str
    arrow_popularidad: str

    color_genero: str

    color_duracion: str
    arrow_duracion: str

    color_direccion: str
    color_actores: str

    color_rating: str

    es_correcto: bool
    estado_partida: str
    intentos_restantes: int


# =========================
# Utilidades
# =========================
def _norm(s: str | None) -> str:
    s = s or ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()


def _arrow(a: int | float | None, b: int | float | None) -> str:
    # retorna "UP" si debes SUBIR para llegar a b, "DOWN" si debes BAJAR
    if a is None or b is None:
        return ""
    if b > a:  # objetivo (b) es MAYOR que el intento (a) -> sube
        return "UP"
    if b < a:  # objetivo (b) es MENOR que el intento (a) -> baja
        return "DOWN"
    return ""


def _band_color(diff: float, band: float) -> ColorCategoria:
    if diff == 0:
        return ColorCategoria.VERDE
    if abs(diff) <= band:
        return ColorCategoria.AMARILLO
    return ColorCategoria.GRIS


# =========================
# Selección de la película (admin)
# =========================
def seleccionar_pelicula_diaria(fecha: date | None = None) -> Pelicula:
    """
    Devuelve la película que el ADMIN fijó para la fecha.
    Si hoy no hay, usa la última seleccionada para no bloquear el juego.
    """
    fecha = fecha or timezone.localdate()
    sel = PeliculaDelDia.objects.filter(fecha=fecha).select_related("pelicula").first()
    if sel:
        return sel.pelicula
    last = PeliculaDelDia.objects.order_by("-fecha").select_related("pelicula").first()
    if last:
        return last.pelicula
    raise RuntimeError("El administrador debe seleccionar una película en el panel.")


# =========================
# Comparadores (7 bloques)
# =========================
def _color_anio(adiv: Pelicula, sec: Pelicula) -> tuple[ColorCategoria, str]:
    color = _band_color(adiv.anio - sec.anio, YEAR_DELTA)
    return color, _arrow(adiv.anio, sec.anio)


def _color_popularidad_por_votos(
    adiv: Pelicula, sec: Pelicula
) -> tuple[ColorCategoria, str]:
    va = adiv.imdb_votes or 0
    vb = sec.imdb_votes or 0
    color = _band_color(va - vb, VOTES_DELTA)  # verde=igual, amarillo si ±100k
    return color, _arrow(va, vb)


def _color_generos(adiv: Pelicula, sec: Pelicula) -> ColorCategoria:
    a = set(_norm(x) for x in adiv.lista_generos())
    b = set(_norm(x) for x in sec.lista_generos())

    inter = a & b
    if not inter:
        return ColorCategoria.GRIS
    # VERDE solo si TODOS los géneros coinciden (conjuntos iguales)
    if a == b:
        return ColorCategoria.VERDE
    # Comparten al menos uno pero no todos -> AMARILLO
    return ColorCategoria.AMARILLO


def _color_duracion(adiv: Pelicula, sec: Pelicula) -> tuple[ColorCategoria, str]:
    da = adiv.duracion_min or 0
    db = sec.duracion_min or 0
    color = _band_color(da - db, DUR_DELTA)
    return color, _arrow(da, db)


def _color_director(adiv: Pelicula, sec: Pelicula) -> ColorCategoria:
    return (
        ColorCategoria.VERDE
        if _norm(adiv.director) == _norm(sec.director)
        else ColorCategoria.GRIS
    )


def _color_actores(adiv: Pelicula, sec: Pelicula) -> ColorCategoria:
    a = set(_norm(x) for x in adiv.lista_actores())
    b = set(_norm(x) for x in sec.lista_actores())

    inter = a & b
    if not inter:
        return ColorCategoria.GRIS
    if a == b:
        return ColorCategoria.VERDE
    return ColorCategoria.AMARILLO


def _color_rating(adiv: Pelicula, sec: Pelicula) -> ColorCategoria:
    ra = float(adiv.imdb_rating) if adiv.imdb_rating is not None else None
    rb = float(sec.imdb_rating) if sec.imdb_rating is not None else None
    if ra is None or rb is None:
        return ColorCategoria.GRIS
    if abs(ra - rb) == 0:
        return ColorCategoria.VERDE
    if abs(ra - rb) <= RATING_DELTA:
        return ColorCategoria.AMARILLO
    return ColorCategoria.GRIS


# =========================
# Registrar intento
# =========================
@transaction.atomic
def registrar_intento(
    jugador: Jugador, pelicula_adivinada: Pelicula
) -> ResultadoIntento:
    fecha = timezone.localdate()
    secreta = seleccionar_pelicula_diaria(fecha)

    partida, _ = Partida.objects.get_or_create(
        jugador=jugador,
        fecha=fecha,
        defaults={"pelicula_secreta": secreta, "intentos_maximos": MAX_INTENTOS},
    )

    # si ya terminó, no permitir más
    if partida.estado != EstadoPartida.EN_CURSO:
        raise ValueError("La partida del día ya finalizó.")

    # Evitar repetir la misma película en la misma partida
    if partida.intentos.filter(pelicula_adivinada=pelicula_adivinada).exists():
        raise ValueError("Ya intentaste esa película en esta partida.")

    # número de intento y límite
    num = partida.intentos.count() + 1
    if num > partida.intentos_maximos:
        partida.estado = EstadoPartida.PERDIDA
        partida.save(update_fields=["estado"])
        raise ValueError("Se alcanzó el máximo de intentos.")

    intento = Intento.objects.create(
        partida=partida, pelicula_adivinada=pelicula_adivinada, numero_intento=num
    )

    # Colores y flechas (7 bloques)
    cA, aA = _color_anio(pelicula_adivinada, secreta)
    cP, aP = _color_popularidad_por_votos(pelicula_adivinada, secreta)
    cG = _color_generos(pelicula_adivinada, secreta)
    cD, aD = _color_duracion(pelicula_adivinada, secreta)
    cDir = _color_director(pelicula_adivinada, secreta)
    cAct = _color_actores(pelicula_adivinada, secreta)
    cR = _color_rating(pelicula_adivinada, secreta)

    # Correcto solo si es EXACTAMENTE la película secreta
    es_ok = pelicula_adivinada.id == secreta.id

    # Guardar feedback
    Feedback.objects.create(
        intento=intento,
        color_anio=cA,
        flecha_anio=aA,
        color_popularidad=cP,
        flecha_popularidad=aP,
        color_genero=cG,
        color_duracion=cD,
        flecha_duracion=aD,
        color_direccion=cDir,
        color_actores=cAct,
        color_rating=cR,
        es_correcto=es_ok,
    )

    # Actualizar estado y rachas
    if es_ok:
        partida.estado = EstadoPartida.GANADA
        jugador.racha_actual += 1
        jugador.racha_maxima = max(jugador.racha_maxima, jugador.racha_actual)
        jugador.save(update_fields=["racha_actual", "racha_maxima"])
    elif num >= partida.intentos_maximos:
        partida.estado = EstadoPartida.PERDIDA
        jugador.racha_actual = 0
        jugador.save(update_fields=["racha_actual"])

    partida.save(update_fields=["estado"])

    return ResultadoIntento(
        intento_id=intento.id,
        numero_intento=num,
        color_anio=cA,
        arrow_anio=aA,
        color_popularidad=cP,
        arrow_popularidad=aP,
        color_genero=cG,
        color_duracion=cD,
        arrow_duracion=aD,
        color_direccion=cDir,
        color_actores=cAct,
        color_rating=cR,
        es_correcto=es_ok,
        estado_partida=partida.estado,
        intentos_restantes=max(0, partida.intentos_maximos - num),
    )
