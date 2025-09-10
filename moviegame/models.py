# moviegame/models.py
from __future__ import annotations
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# =========================
# Enums
# =========================
class ColorCategoria(models.TextChoices):
    VERDE = "VERDE", "Verde"
    AMARILLO = "AMARILLO", "Amarillo"
    GRIS = "GRIS", "Gris"


class EstadoPartida(models.TextChoices):
    EN_CURSO = "EN_CURSO", "En curso"
    GANADA = "GANADA", "Ganada"
    PERDIDA = "PERDIDA", "Perdida"


class DireccionFlecha(models.TextChoices):
    UP = "UP", "Arriba"  # valor del intento es MAYOR que el objetivo
    DOWN = "DOWN", "Abajo"  # valor del intento es MENOR que el objetivo
    NONE = "", "Igual"  # sin flecha (coincide)


# =========================
# Película
# =========================
class Pelicula(models.Model):
    # Mantenemos el nombre de campo 'anio' (compatibilidad), etiqueta visible "año"
    titulo = models.CharField(max_length=255, db_index=True)
    anio = models.PositiveIntegerField("año", db_index=True)

    genero = models.CharField(max_length=255, blank=True)  # "Action, Drama, ..."
    director = models.CharField(max_length=255, blank=True)
    actores = models.CharField(
        max_length=512, blank=True
    )  # "Actor1, Actor2, Actor3, ..."
    duracion_min = models.PositiveIntegerField("duración (min)", default=0)

    # Datos de OMDb que usaremos en el juego
    imdb_rating = models.DecimalField(
        "IMDb rating", max_digits=3, decimal_places=1, null=True, blank=True
    )  # 0.0..10.0
    imdb_votes = models.PositiveIntegerField(
        "IMDb votes", null=True, blank=True
    )  # se usará como “popularidad”

    imdb_id = models.CharField(max_length=16, blank=True, null=True, unique=True)
    poster_url = models.URLField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["titulo"]
        constraints = [
            models.UniqueConstraint(fields=["titulo", "anio"], name="uniq_titulo_anio"),
        ]

    def __str__(self):
        return f"{self.titulo} ({self.anio})"

    # Helpers para tomar los "3 principales"
    def lista_generos(self) -> list[str]:
        return [g.strip() for g in self.genero.split(",") if g.strip()][:3]

    def lista_actores(self) -> list[str]:
        return [a.strip() for a in self.actores.split(",") if a.strip()][:3]


# =========================
# Jugador (perfil)
# =========================
class Jugador(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="jugador")
    racha_actual = models.PositiveIntegerField(default=0)
    racha_maxima = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.user.username


# =========================
# Partida (una por día por jugador)
# =========================
class Partida(models.Model):
    jugador = models.ForeignKey(
        Jugador, on_delete=models.CASCADE, related_name="partidas"
    )
    pelicula_secreta = models.ForeignKey(
        Pelicula, on_delete=models.PROTECT, related_name="como_secreta_en"
    )
    fecha = models.DateField(db_index=True, default=timezone.localdate)
    estado = models.CharField(
        max_length=12, choices=EstadoPartida.choices, default=EstadoPartida.EN_CURSO
    )
    intentos_maximos = models.PositiveIntegerField(default=10)  # “10 guesses”
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("jugador", "fecha")]  # una partida por día por jugador
        ordering = ["-fecha", "-creado_en"]

    def __str__(self):
        return f"Partida {self.jugador} {self.fecha} ({self.estado})"


# =========================
# Intento
# =========================
class Intento(models.Model):
    partida = models.ForeignKey(
        Partida, on_delete=models.CASCADE, related_name="intentos"
    )
    pelicula_adivinada = models.ForeignKey(
        Pelicula, on_delete=models.PROTECT, related_name="como_adivinada_en"
    )
    numero_intento = models.PositiveIntegerField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("partida", "numero_intento")]
        ordering = ["numero_intento"]

    def __str__(self):
        return f"Intento {self.numero_intento} de {self.partida}"


# =========================
# Feedback (1 a 1 con Intento)
# =========================
class Feedback(models.Model):
    intento = models.OneToOneField(
        Intento, on_delete=models.CASCADE, related_name="feedback"
    )

    # 1) Año (color + flecha)
    color_anio = models.CharField(
        max_length=10, choices=ColorCategoria.choices, default=ColorCategoria.GRIS
    )
    flecha_anio = models.CharField(
        max_length=4,
        choices=DireccionFlecha.choices,
        blank=True,
        default=DireccionFlecha.NONE,
    )

    # 2) Popularidad por votos (color + flecha) — usamos imdb_votes
    color_popularidad = models.CharField(
        max_length=10, choices=ColorCategoria.choices, default=ColorCategoria.GRIS
    )
    flecha_popularidad = models.CharField(
        max_length=4,
        choices=DireccionFlecha.choices,
        blank=True,
        default=DireccionFlecha.NONE,
    )

    # 3) Géneros (verde si comparte alguno de los 3; si no, gris)
    color_genero = models.CharField(
        max_length=10, choices=ColorCategoria.choices, default=ColorCategoria.GRIS
    )

    # 4) Duración en minutos (color + flecha)
    color_duracion = models.CharField(
        max_length=10, choices=ColorCategoria.choices, default=ColorCategoria.GRIS
    )
    flecha_duracion = models.CharField(
        max_length=4,
        choices=DireccionFlecha.choices,
        blank=True,
        default=DireccionFlecha.NONE,
    )

    # 5) Director (solo gris/verde)
    color_direccion = models.CharField(
        max_length=10, choices=ColorCategoria.choices, default=ColorCategoria.GRIS
    )

    # 6) Actores (verde si coincide alguno de los 3; si no, gris)
    color_actores = models.CharField(
        max_length=10, choices=ColorCategoria.choices, default=ColorCategoria.GRIS
    )

    # 7) IMDb Rating (verde exacto; amarillo si |diff| ≤ 1.0; gris si > 1.0)
    color_rating = models.CharField(
        max_length=10, choices=ColorCategoria.choices, default=ColorCategoria.GRIS
    )

    es_correcto = models.BooleanField(default=False)

    def __str__(self):
        return (
            f"Feedback intento {self.intento_id} ({'✔' if self.es_correcto else '✗'})"
        )


# =========================
# Selección por día (admin)
# =========================
class PeliculaDelDia(models.Model):
    fecha = models.DateField(unique=True, db_index=True, default=timezone.localdate)
    pelicula = models.ForeignKey(
        Pelicula, on_delete=models.PROTECT, related_name="seleccionada_como_del_dia"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.fecha} → {self.pelicula}"
