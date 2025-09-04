# created by Valentina
from __future__ import annotations
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# --- Enums ---
class ColorCategoria(models.TextChoices):
    VERDE = "VERDE", "Verde"
    AMARILLO = "AMARILLO", "Amarillo"
    GRIS = "GRIS", "Gris"

class EstadoPartida(models.TextChoices):
    EN_CURSO = "EN_CURSO", "En curso"
    GANADA = "GANADA", "Ganada"
    PERDIDA = "PERDIDA", "Perdida"

# --- Película ---
class Pelicula(models.Model):
    titulo = models.CharField(max_length=255, db_index=True, unique=True)
    anio = models.PositiveIntegerField(db_index=True)
    genero = models.CharField(max_length=255, blank=True)      # "Action, Drama"
    director = models.CharField(max_length=255, blank=True)
    actores = models.CharField(max_length=512, blank=True)     # "Actor1, Actor2, ..."
    imdb_id = models.CharField(max_length=16, blank=True, null=True, unique=True)
    poster_url = models.URLField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["titulo"]

    def __str__(self):
        return f"{self.titulo} ({self.anio})"

    def lista_generos(self) -> list[str]:
        return [g.strip() for g in self.genero.split(",") if g.strip()]

    def lista_actores(self) -> list[str]:
        return [a.strip() for a in self.actores.split(",") if a.strip()]

# --- Jugador (perfil) ---
class Jugador(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="jugador")
    racha_actual = models.PositiveIntegerField(default=0)
    racha_maxima = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.user.username

# --- Partida (una por día por jugador) ---
class Partida(models.Model):
    jugador = models.ForeignKey(Jugador, on_delete=models.CASCADE, related_name="partidas")
    pelicula_secreta = models.ForeignKey(Pelicula, on_delete=models.PROTECT, related_name="como_secreta_en")
    fecha = models.DateField(db_index=True, default=timezone.localdate)
    estado = models.CharField(max_length=12, choices=EstadoPartida.choices, default=EstadoPartida.EN_CURSO)
    intentos_maximos = models.PositiveIntegerField(default=6)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("jugador", "fecha")]  # una partida por día por jugador
        ordering = ["-fecha", "-creado_en"]

    def __str__(self):
        return f"Partida {self.jugador} {self.fecha} ({self.estado})"

# --- Intento ---
class Intento(models.Model):
    partida = models.ForeignKey(Partida, on_delete=models.CASCADE, related_name="intentos")
    pelicula_adivinada = models.ForeignKey(Pelicula, on_delete=models.PROTECT, related_name="como_adivinada_en")
    numero_intento = models.PositiveIntegerField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("partida", "numero_intento")]
        ordering = ["numero_intento"]

    def __str__(self):
        return f"Intento {self.numero_intento} de {self.partida}"

# --- Feedback (1 a 1 con Intento) ---
class Feedback(models.Model):
    intento = models.OneToOneField(Intento, on_delete=models.CASCADE, related_name="feedback")
    color_anio = models.CharField(max_length=10, choices=ColorCategoria.choices)
    color_genero = models.CharField(max_length=10, choices=ColorCategoria.choices)
    color_direccion = models.CharField(max_length=10, choices=ColorCategoria.choices)  # director
    color_actores = models.CharField(max_length=10, choices=ColorCategoria.choices)
    es_correcto = models.BooleanField(default=False)

    def __str__(self):
        return f"Feedback intento {self.intento_id} ({'✔' if self.es_correcto else '✗'})"
