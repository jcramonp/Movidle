from __future__ import annotations

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect, get_object_or_404, resolve_url
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseServerError
from django.views.decorators.http import require_POST
from django.db.models import Count
from django.utils import timezone
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db.models import Q


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
    """
    Landing: mensaje + posters famosos + CTA.
    Enviamos 'famous_movies' con lo más conocido (votos/rating) y con poster.
    """
    # Ajusta el límite como prefieras (entre 6–18 luce bien con el layout)
    limit = 12

    famous_qs = (
        Pelicula.objects
        .filter(
            ~Q(poster_url__isnull=True),
            ~Q(poster_url__exact=""),
            imdb_votes__isnull=False,
        )
        .order_by("-imdb_votes", "-imdb_rating")[:limit]
        .only("id", "titulo", "anio", "poster_url", "imdb_votes", "imdb_rating")
    )

    # Normalizamos a un dict simple que el template consume directo
    famous_movies = [
        {
            "title": m.titulo,
            "year": m.anio,
            "poster_url": m.poster_url,
        }
        for m in famous_qs
    ]

    return render(
        request,
        "moviegame/home.html",
        {
            "famous_movies": famous_movies,
        },
    )


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

# --- Login personalizado: admin -> panel, jugador -> next o fallback ---
class MovidleLoginView(LoginView):
    template_name = "moviegame/login.html"
    redirect_authenticated_user = True  # si ya está logueado, lo redirige

    def get_success_url(self):
        user = self.request.user

        # Admin siempre al panel
        if user.is_staff:
            return reverse_lazy("moviegame:admin_dashboard")

        # Jugador: respetar ?next= si es seguro
        redirect_to = self.request.POST.get("next") or self.request.GET.get("next")
        if redirect_to and url_has_allowed_host_and_scheme(
            redirect_to, allowed_hosts={self.request.get_host()}
        ):
            return redirect_to

        # Fallback (tu valor por defecto)
        return resolve_url(getattr(settings, "LOGIN_REDIRECT_URL", "moviegame:home"))


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

###################### API PÚBLICA DE PELÍCULAS #########################

from .models import Pelicula

def _coalesce(*vals, default=None):
    for v in vals:
        if v not in (None, "", []):
            return v
    return default


def _genres_to_text(m):
    try:
        names = m.lista_generos()
        return ", ".join(names) if names else ""
    except Exception:
        g = getattr(m, "genero", "")
        return g or ""

def _movie_to_public_dict(m, request):
    rating = float(m.imdb_rating) if m.imdb_rating is not None else None

    return {
        "id": m.id,
        "title": m.titulo,
        "year": m.anio,
        "genres": _genres_to_text(m),
        "runtime_min": int(m.duracion_min or 0),
        "imdb_rating": rating,
        "popularity_votes": int(m.imdb_votes or 0),
        "app_url": request.build_absolute_uri(reverse("moviegame:howto")),
    }

@require_GET
def api_public_movies(request):

    q = (request.GET.get("q") or "").strip()
    try:
        limit = int(request.GET.get("limit", 20))
    except ValueError:
        limit = 20
    limit = max(1, min(limit, 100))

    qs = Pelicula.objects.all()

    if q:
        qs = qs.filter(titulo__icontains=q)

    order_fields = []
    if hasattr(Pelicula, "popularidad_votos"):
        order_fields.append("-popularidad_votos")
    if hasattr(Pelicula, "imdb_rating"):
        order_fields.append("-imdb_rating")
    order_fields = order_fields or ["-id"]

    qs = qs.order_by(*order_fields)[:limit]

    results = [_movie_to_public_dict(m, request) for m in qs]
    data = {"provider": "Movidle", "count": len(results), "results": results}

    resp = JsonResponse(data, json_dumps_params={"ensure_ascii": False})
    resp["Access-Control-Allow-Origin"] = "*"
    return resp

# --- Página informativa/API Explorer ---------------------------------------
from django.shortcuts import render
from django.urls import reverse
from django.http import HttpRequest

def _abs(request: HttpRequest, path: str) -> str:
    return request.build_absolute_uri(path)

def api_info(request):
    endpoints = {
        "movies": _abs(request, reverse("moviegame:api_public_movies")),

    }
    ctx = {
        "endpoints": endpoints,
        "sample_movies_url": f'{endpoints["movies"]}?limit=12',
    }
    return render(request, "moviegame/api_info.html", ctx)

# ---------------- API DE ALIADOS ----------------------

API_BASE = "https://ctrlstore-service-420478585093.us-central1.run.app"
IN_STOCK_URL = f"{API_BASE}/api/products/in-stock/"

def productos_aliados(request):
    # Permite filtrar destacados vía ?featured=true
    params = {}
    featured = request.GET.get("featured")
    if featured in ("true", "1", "yes"):
        params["featured"] = featured

    try:
        r = requests.get(IN_STOCK_URL, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        products = data.get("results", [])[:100]  # el endpoint ya limita a 100
        # Construir URL absoluta de detalle
        for p in products:
            rel = p.get("detail_url") or ""
            p["detail_absolute"] = f"{API_BASE}{rel}"
        context = {
            "products": products,
            "featured": bool(params.get("featured")),
        }
        return render(request, "moviegame/aliados.html", {"products": products, "featured": "featured" in params})

    except requests.RequestException as e:
        # Puedes registrar el error con logging
        return HttpResponseServerError("No fue posible cargar los productos aliados.")