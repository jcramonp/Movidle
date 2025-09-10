from __future__ import annotations

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.db.models import Count
from django.utils import timezone

from .models import (
    Pelicula,
    Partida,
    Jugador,
    Feedback,
    Intento,
    EstadoPartida,
    PeliculaDelDia,
)
from .services.game_service import (
    registrar_intento,
    seleccionar_pelicula_diaria,
    MAX_INTENTOS,
)


# --------------------------
#  PÁGINAS
# --------------------------


def home_view(request):
    """Landing: logo, tagline y botón Play."""
    return render(request, "moviegame/home.html")


def register_view(request):
    """Registro simple con UserCreationForm."""
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
    """
    Página de juego. Crea (o recupera) la partida del día para el jugador actual.
    Si el admin no ha seleccionado película, mostramos mensaje.
    """
    jugador = request.user.jugador
    if request.user.is_staff:
        return redirect("moviegame:admin_dashboard")

    jugador = getattr(request.user, "jugador", None)

    if jugador is None:
        jugador = Jugador.objects.create(user=request.user)

    fecha = timezone.localdate()

    try:
        secreta = seleccionar_pelicula_diaria(fecha)
    except RuntimeError as e:
        # No hay selección: mostramos aviso en la plantilla
        return render(
            request,
            "moviegame/game.html",
            {
                "no_game_msg": str(e),
                "guess_now": 1,
                "max_intentos": MAX_INTENTOS,
            },
        )

    partida, _ = Partida.objects.get_or_create(
        jugador=jugador,
        fecha=fecha,
        defaults={"pelicula_secreta": secreta, "intentos_maximos": MAX_INTENTOS},
    )

    guess_now = partida.intentos.count() + 1
    return render(
        request,
        "moviegame/game.html",
        {
            "guess_now": guess_now,
            "max_intentos": MAX_INTENTOS,
        },
    )


@login_required
def stats_view(request):
    """Estadísticas básicas del jugador (para tu modal)."""
    jugador = request.user.jugador
    partidas = jugador.partidas.all()
    ganadas = partidas.filter(estado=EstadoPartida.GANADA).count()
    perdidas = partidas.filter(estado=EstadoPartida.PERDIDA).count()
    distribucion = (
        Intento.objects.filter(partida__jugador=jugador, feedback__es_correcto=True)
        .values("numero_intento")
        .annotate(cnt=Count("id"))
        .order_by("numero_intento")
    )
    return render(
        request,
        "moviegame/stats.html",
        {
            "jugador": jugador,
            "ganadas": ganadas,
            "perdidas": perdidas,
            "distribucion": list(distribucion),
        },
    )


# --------------------------
#  PANEL ADMIN (simple)
# --------------------------


def _es_staff(u):
    return u.is_staff


@user_passes_test(_es_staff)
def admin_dashboard(request):
    """Panel ligero: muestra métricas del día y la película seleccionada."""
    hoy = timezone.localdate()
    try:
        secreta = seleccionar_pelicula_diaria(hoy)
    except RuntimeError:
        secreta = None

    total_intentos = Intento.objects.filter(partida__fecha=hoy).count()
    total_partidas = Partida.objects.filter(fecha=hoy).count()
    win = Partida.objects.filter(fecha=hoy, estado=EstadoPartida.GANADA).count()
    tasa_acierto = round(win * 100 / total_partidas, 1) if total_partidas else 0
    top_pelis = (
        Intento.objects.filter(partida__fecha=hoy)
        .values("pelicula_adivinada__titulo")
        .annotate(cnt=Count("id"))
        .order_by("-cnt")[:10]
    )

    return render(
        request,
        "moviegame/admin_dashboard.html",
        {
            "hoy": hoy,
            "total_intentos": total_intentos,
            "total_partidas": total_partidas,
            "tasa_acierto": tasa_acierto,
            "top_pelis": top_pelis,
            "secreta": secreta,
            "navbar_mode": "admin",
        },
    )


@user_passes_test(_es_staff)
@require_POST
def admin_set_daily(request):
    """
    Admin: fija la película de HOY (si no hay, crea; si hay, actualiza).
    Espera POST con 'pelicula_id'.
    """
    pid = request.POST.get("pelicula_id")
    if not pid:
        return HttpResponseBadRequest("Falta pelicula_id")
    peli = get_object_or_404(Pelicula, id=pid)

    fecha = timezone.localdate()
    PeliculaDelDia.objects.update_or_create(fecha=fecha, defaults={"pelicula": peli})
    return redirect("moviegame:admin_dashboard")


# --------------------------
#  API
# --------------------------


@login_required
@require_POST
def api_intentos(request):
    """
    Registra un intento y devuelve feedback para los 7 bloques.
    Keys devueltas (todas con 'Año' y acentos):
      - numero_intento, intentosRestantes, estadoPartida
      - colorAño + arrowAño
      - colorPopularidad + arrowPopularidad  (basado en imdb_votes)
      - colorGeneros
      - colorDuración + arrowDuración
      - colorDirector
      - colorActores
      - colorRating
      - (si terminó) revealTitle, revealAño, revealPoster
    """
    jugador = request.user.jugador
    fecha = timezone.localdate()

    # Si ya terminó, devolvemos revelación inmediata
    partida_existente = (
        Partida.objects.filter(jugador=jugador, fecha=fecha)
        .select_related("pelicula_secreta")
        .first()
    )
    if partida_existente and partida_existente.estado != EstadoPartida.EN_CURSO:
        s = partida_existente.pelicula_secreta
        return JsonResponse(
            {
                "error": "La partida del día ya finalizó.",
                "estadoPartida": partida_existente.estado,
                "revealTitle": s.titulo,
                "revealAño": s.anio,
                "revealPoster": s.poster_url,
                "intentosRestantes": 0,
            },
            status=200,
        )

    # Resolver película del intento
    pid = request.POST.get("pelicula_id")
    titulo = (request.POST.get("titulo") or "").strip()
    if pid:
        peli = get_object_or_404(Pelicula, id=pid)
    elif titulo:
        try:
            peli = Pelicula.objects.get(titulo__iexact=titulo)
        except Pelicula.DoesNotExist:
            return HttpResponseBadRequest("Película no encontrada")
    else:
        return HttpResponseBadRequest("Faltan parámetros")

    # Registrar y responder
    try:
        res = registrar_intento(jugador, peli)
    except ValueError as e:
        partida = (
            Partida.objects.filter(jugador=jugador, fecha=fecha)
            .select_related("pelicula_secreta")
            .first()
        )
        payload = {"error": str(e)}
        if partida and partida.estado != EstadoPartida.EN_CURSO:
            s = partida.pelicula_secreta
            payload.update(
                {
                    "estadoPartida": partida.estado,
                    "revealTitle": s.titulo,
                    "revealAño": s.anio,
                    "revealPoster": s.poster_url,
                    "intentosRestantes": 0,
                }
            )
        return JsonResponse(payload, status=200)

    reveal = {}
    if res.estado_partida != EstadoPartida.EN_CURSO:
        # Traemos la secreta para revelar
        partida = Partida.objects.get(jugador=jugador, fecha=fecha)
        s = partida.pelicula_secreta
        reveal = {
            "revealTitle": s.titulo,
            "revealAño": s.anio,
            "revealPoster": s.poster_url,
        }

    return JsonResponse(
        {
            "numero_intento": res.numero_intento,
            "intentosRestantes": res.intentos_restantes,
            "estadoPartida": res.estado_partida,
            "colorAño": res.color_anio,
            "arrowAño": res.arrow_anio,
            "colorPopularidad": res.color_popularidad,
            "arrowPopularidad": res.arrow_popularidad,
            "colorGeneros": res.color_genero,
            "colorDuración": res.color_duracion,
            "arrowDuración": res.arrow_duracion,
            "colorDirector": res.color_direccion,
            "colorActores": res.color_actores,
            "colorRating": res.color_rating,
            # ⬇⬇⬇  VALORES DEL INTENTO (PISTAS)  ⬇⬇⬇
            "valAño": int(peli.anio) if peli.anio is not None else None,
            "valPopularidad": int(peli.imdb_votes or 0),
            "valGeneros": ", ".join(peli.lista_generos()),
            "valDuración": int(peli.duracion_min or 0),
            "valDirector": peli.director,
            "valActores": ", ".join(peli.lista_actores()),
            "valRating": (
                float(peli.imdb_rating) if peli.imdb_rating is not None else None
            ),
            **reveal,
        }
    )


@login_required
def api_autocomplete(request):
    """
    Sugerencias de películas (para el buscador del juego).
    - Prioriza títulos que EMPIEZAN por q, luego los que CONTIENEN q (sin duplicar).
    - Solo devuelve películas con datos suficientes para jugar.
    - Ordena por imdb_votes DESC para mostrar las más conocidas primero.
    Parámetros: q (texto), limit (por defecto 20)
    """
    q = (request.GET.get("q") or "").strip()
    try:
        limit = int(request.GET.get("limit", 20))
    except ValueError:
        limit = 20

    if not q:
        return JsonResponse({"results": []})

    base = Pelicula.objects.filter(
        imdb_votes__isnull=False, imdb_rating__isnull=False
    ).order_by("-imdb_votes")

    # Empiezan por q
    starts = list(
        base.filter(titulo__istartswith=q).values("id", "titulo", "anio")[:limit]
    )

    results = starts[:]
    if len(results) < limit:
        left = limit - len(results)
        contains = (
            base.filter(titulo__icontains=q)
            .exclude(id__in=[r["id"] for r in results])
            .values("id", "titulo", "anio")[:left]
        )
        results.extend(list(contains))

    return JsonResponse({"results": results})


def howto_view(request):
    return render(request, "moviegame/howto.html")
