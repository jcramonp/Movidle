from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import hashlib
import unicodedata
from django.db import transaction
from django.utils import timezone
from ..models import (
    Pelicula, Jugador, Partida, Intento, Feedback,
    ColorCategoria, EstadoPartida
)

@dataclass
class ResultadoIntento:
    intento_id: int
    numero_intento: int
    color_genero: str
    color_anio: str
    color_direccion: str
    color_actores: str
    es_correcto: bool
    estado_partida: str
    intentos_restantes: int

# --- utilidades ---
def _norm(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()

def _apellido(nombre: str) -> str:
    partes = [p for p in _norm(nombre).split() if p]
    return partes[-1] if partes else ""

# --- selección determinística de la película del día ---
def seleccionar_pelicula_diaria(fecha: date | None = None) -> Pelicula:
    fecha = fecha or timezone.localdate()
    n = Pelicula.objects.count()
    if n == 0:
        raise RuntimeError("No hay películas en la base de datos.")
    # hash de la fecha → índice
    h = int(hashlib.sha256(str(fecha).encode()).hexdigest(), 16)
    idx = h % n
    return Pelicula.objects.all().order_by("id")[idx]

def _color_anio(adivinada: Pelicula, secreta: Pelicula) -> ColorCategoria:
    if adivinada.anio == secreta.anio:
        return ColorCategoria.VERDE
    if abs(adivinada.anio - secreta.anio) <= 2:
        return ColorCategoria.AMARILLO
    return ColorCategoria.GRIS

def _color_genero(adivinada: Pelicula, secreta: Pelicula) -> ColorCategoria:
    ga = adivinada.lista_generos()
    gs = secreta.lista_generos()
    if not ga or not gs:
        return ColorCategoria.GRIS
    if ga and gs and ga[0].lower() == gs[0].lower():           # género principal igual
        return ColorCategoria.VERDE
    if set(map(_norm, ga)) & set(map(_norm, gs)):               # comparten alguno
        return ColorCategoria.AMARILLO
    return ColorCategoria.GRIS

def _color_director(adivinada: Pelicula, secreta: Pelicula) -> ColorCategoria:
    if _norm(adivinada.director) == _norm(secreta.director):
        return ColorCategoria.VERDE
    if _apellido(adivinada.director) and _apellido(adivinada.director) == _apellido(secreta.director):
        return ColorCategoria.AMARILLO
    return ColorCategoria.GRIS

def _color_actores(adivinada: Pelicula, secreta: Pelicula) -> ColorCategoria:
    a = set(map(_norm, adivinada.lista_actores()))
    b = set(map(_norm, secreta.lista_actores()))
    inter = a & b
    if len(inter) >= 2:
        return ColorCategoria.VERDE
    if len(inter) == 1:
        return ColorCategoria.AMARILLO
    return ColorCategoria.GRIS

@transaction.atomic
def registrar_intento(jugador: Jugador, pelicula_adivinada: Pelicula) -> ResultadoIntento:
    # obtiene o crea la partida del día
    fecha = timezone.localdate()
    secreta = seleccionar_pelicula_diaria(fecha)
    partida, _ = Partida.objects.get_or_create(
        jugador=jugador, fecha=fecha,
        defaults={"pelicula_secreta": secreta}
    )
    # si ya terminó, no permitir más
    if partida.estado != EstadoPartida.EN_CURSO:
        raise ValueError("La partida del día ya finalizó.")

    # número de intento
    num = partida.intentos.count() + 1
    if num > partida.intentos_maximos:
        partida.estado = EstadoPartida.PERDIDA
        partida.save(update_fields=["estado"])
        raise ValueError("Se alcanzó el máximo de intentos.")

    intento = Intento.objects.create(
        partida=partida, pelicula_adivinada=pelicula_adivinada, numero_intento=num
    )

    c_anio = _color_anio(pelicula_adivinada, partida.pelicula_secreta)
    c_gen = _color_genero(pelicula_adivinada, partida.pelicula_secreta)
    c_dir = _color_director(pelicula_adivinada, partida.pelicula_secreta)
    c_act = _color_actores(pelicula_adivinada, partida.pelicula_secreta)

    es_ok = (
        c_anio == ColorCategoria.VERDE and
        c_gen == ColorCategoria.VERDE and
        c_dir == ColorCategoria.VERDE and
        c_act == ColorCategoria.VERDE
    )

    Feedback.objects.create(
        intento=intento,
        color_anio=c_anio, color_genero=c_gen,
        color_direccion=c_dir, color_actores=c_act,
        es_correcto=es_ok
    )

    # actualizar estado/rachas
    if es_ok:
        partida.estado = EstadoPartida.GANADA
        j = jugador
        j.racha_actual += 1
        j.racha_maxima = max(j.racha_maxima, j.racha_actual)
        j.save(update_fields=["racha_actual", "racha_maxima"])
    elif num >= partida.intentos_maximos:
        partida.estado = EstadoPartida.PERDIDA
        jugador.racha_actual = 0
        jugador.save(update_fields=["racha_actual"])

    partida.save(update_fields=["estado"])

    return ResultadoIntento(
        intento_id=intento.id,
        numero_intento=num,
        color_genero=c_gen, color_anio=c_anio,
        color_direccion=c_dir, color_actores=c_act,
        es_correcto=es_ok,
        estado_partida=partida.estado,
        intentos_restantes=max(0, partida.intentos_maximos - num)
    )
