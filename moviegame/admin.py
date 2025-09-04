from django.contrib import admin
from .models import Pelicula, Jugador, Partida, Intento, Feedback

@admin.register(Pelicula)
class PeliculaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "anio", "director", "imdb_id")
    search_fields = ("titulo", "director", "actores", "imdb_id", "genero")
    list_filter = ("anio",)

@admin.register(Jugador)
class JugadorAdmin(admin.ModelAdmin):
    list_display = ("user", "racha_actual", "racha_maxima")
    search_fields = ("user__username",)

class IntentoInline(admin.TabularInline):
    model = Intento
    extra = 0
    readonly_fields = ("numero_intento", "pelicula_adivinada", "creado_en")

@admin.register(Partida)
class PartidaAdmin(admin.ModelAdmin):
    list_display = ("jugador", "fecha", "pelicula_secreta", "estado")
    list_filter = ("fecha", "estado")
    inlines = [IntentoInline]

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("intento", "color_anio", "color_genero", "color_direccion", "color_actores", "es_correcto")
