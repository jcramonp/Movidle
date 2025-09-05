from __future__ import annotations
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.db.models import Count
from django.utils import timezone

from .models import Pelicula, Partida, Jugador, Feedback, Intento, EstadoPartida
from .services.game_service import registrar_intento, seleccionar_pelicula_diaria

# --- Pages ---
def register_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("moviegame:login")
    else:
        form = UserCreationForm()
    return render(request, "moviegame/register.html", {"form": form})

@login_required
def game_view(request):
    jugador = request.user.jugador
    fecha = timezone.localdate()
    secreta = seleccionar_pelicula_diaria(fecha)
    partida, _ = Partida.objects.get_or_create(
        jugador=jugador, fecha=fecha, defaults={"pelicula_secreta": secreta}
    )
    intentos = partida.intentos.select_related("feedback", "pelicula_adivinada").all()

    # ► SOLO revelar si la partida terminó
    reveal = None
    if partida.estado != EstadoPartida.EN_CURSO:
        reveal = {
            "titulo": partida.pelicula_secreta.titulo,
            "anio": partida.pelicula_secreta.anio,
            "poster": partida.pelicula_secreta.poster_url,
        }

    return render(request, "moviegame/game.html", {
        "partida": partida,
        "intentos": intentos,
        "intentos_restantes": max(0, partida.intentos_maximos - intentos.count()),
        "reveal": reveal,   # ← clave nueva
    })


@login_required
def stats_view(request):
    jugador = request.user.jugador
    partidas = jugador.partidas.all()
    ganadas = partidas.filter(estado=EstadoPartida.GANADA).count()
    perdidas = partidas.filter(estado=EstadoPartida.PERDIDA).count()
    distribucion = Intento.objects.filter(partida__jugador=jugador, feedback__es_correcto=True) \
                                  .values("numero_intento") \
                                  .annotate(cnt=Count("id")).order_by("numero_intento")
    return render(request, "moviegame/stats.html", {
        "jugador": jugador,
        "ganadas": ganadas, "perdidas": perdidas,
        "distribucion": list(distribucion),
    })

# panel sencillo (no el admin de Django)
def _es_staff(u): return u.is_staff

@user_passes_test(_es_staff)
def admin_dashboard(request):
    hoy = timezone.localdate()
    secreta = seleccionar_pelicula_diaria(hoy)

    total_intentos = Intento.objects.filter(partida__fecha=hoy).count()
    total_partidas = Partida.objects.filter(fecha=hoy).count()
    win = Partida.objects.filter(fecha=hoy, estado=EstadoPartida.GANADA).count()
    tasa_acierto = round(win * 100 / total_partidas, 1) if total_partidas else 0
    top_pelis = Intento.objects.filter(partida__fecha=hoy) \
                               .values("pelicula_adivinada__titulo") \
                               .annotate(cnt=Count("id")).order_by("-cnt")[:10]
    return render(request, "moviegame/admin_dashboard.html", {
        "hoy": hoy, "total_intentos": total_intentos,
        "total_partidas": total_partidas, "tasa_acierto": tasa_acierto,
        "top_pelis": top_pelis, "secreta": secreta,
    })


# --- API ---
@login_required
@require_POST
def api_registrar_intento(request):
    jugador = request.user.jugador
    fecha = timezone.localdate()

    # Si la partida ya estaba finalizada, respondemos con la revelación.
    partida_existente = Partida.objects.filter(jugador=jugador, fecha=fecha).select_related("pelicula_secreta").first()
    if partida_existente and partida_existente.estado != EstadoPartida.EN_CURSO:
        s = partida_existente.pelicula_secreta
        return JsonResponse({
            "error": "La partida del día ya finalizó.",
            "estadoPartida": partida_existente.estado,
            "revealTitle": s.titulo, "revealYear": s.anio, "revealPoster": s.poster_url,
            "intentosRestantes": 0,
        }, status=200)

    # Resolver la película ingresada
    pid = request.POST.get("pelicula_id")
    titulo = request.POST.get("titulo")
    if pid:
        peli = get_object_or_404(Pelicula, id=pid)
    elif titulo:
        try:
            peli = Pelicula.objects.get(titulo__iexact=titulo.strip())
        except Pelicula.DoesNotExist:
            return HttpResponseBadRequest("Película no encontrada")
    else:
        return HttpResponseBadRequest("Faltan parámetros")

    # Intentar registrar
    try:
        res = registrar_intento(jugador, peli)
    except ValueError as e:
        # Puede ser que justo quedó PERDIDA por máximo de intentos;
        # devolvemos la revelación si ya terminó.
        partida = Partida.objects.get(jugador=jugador, fecha=fecha)
        if partida.estado != EstadoPartida.EN_CURSO:
            s = partida.pelicula_secreta
            return JsonResponse({
                "error": str(e),
                "estadoPartida": partida.estado,
                "revealTitle": s.titulo, "revealYear": s.anio, "revealPoster": s.poster_url,
                "intentosRestantes": 0,
            }, status=200)
        return JsonResponse({"error": str(e)}, status=400)

    # Si terminó (ganó o perdió), incluir la revelación
    reveal = {}
    if res.estado_partida != EstadoPartida.EN_CURSO:
        partida = Partida.objects.get(jugador=jugador, fecha=fecha)
        s = partida.pelicula_secreta
        reveal = {"revealTitle": s.titulo, "revealYear": s.anio, "revealPoster": s.poster_url}

    return JsonResponse({
        "intento_id": res.intento_id,
        "numero_intento": res.numero_intento,
        "colorGenero": res.color_genero,
        "colorAnio": res.color_anio,
        "colorDirector": res.color_direccion,
        "colorActores": res.color_actores,
        "esCorrecto": res.es_correcto,
        "estadoPartida": res.estado_partida,
        "intentosRestantes": res.intentos_restantes,
        **reveal,  # ← solo si aplica
    })


@login_required
def api_autocomplete(request):
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"results": []})
    qs = Pelicula.objects.filter(titulo__icontains=q).order_by("titulo")[:12]
    return JsonResponse({
        "results": [{"id": p.id, "titulo": p.titulo, "anio": p.anio} for p in qs]
    })
