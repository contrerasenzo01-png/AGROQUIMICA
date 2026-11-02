from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .permissions import MENU, permisos_ui, puede, rutas_denegadas


# ------------------------------------------------------------
# UBICACIÓN ACTUAL (barra superior)
# Sale del MENU de permissions.py: el mismo que arma el menú
# lateral. Así la ruta siempre coincide con el menú, y cada
# pantalla nueva que se agregue al MENU aparece sola.
# ------------------------------------------------------------

# Pantallas que no están en el menú lateral: url_name -> (sección, pantalla)
PANTALLAS_EXTRA = {
    'panel_principal': (None, 'Panel principal'),
    'mis_permisos': ('Mi cuenta', 'Mis permisos'),
    'cambiar_contrasena': ('Mi cuenta', 'Cambiar contraseña'),
}


def _titulo_seccion(titulo):
    """'ADMINISTRACIÓN' -> 'Administración'."""
    return titulo.capitalize()


def _pantallas_del_menu():
    """Lista de (url_name, ruta, sección, pantalla) de todo el MENU."""

    pantallas = []

    for titulo, items in MENU:
        for modulo, nombre_url, icono, texto in items:
            try:
                ruta = reverse(nombre_url)
            except NoReverseMatch:
                ruta = ''

            pantallas.append((nombre_url, ruta, _titulo_seccion(titulo), texto))

    return pantallas


def _ubicacion(request):
    """Lista de tramos [{'nombre': ..., 'url': ...}] después del ícono de inicio."""

    match = getattr(request, 'resolver_match', None)
    nombre_url = match.url_name if match else ''

    # 1. Pantallas fuera del menú (panel, mi cuenta).
    if nombre_url in PANTALLAS_EXTRA:
        seccion, pantalla = PANTALLAS_EXTRA[nombre_url]
        tramos = [{'nombre': seccion, 'url': None}] if seccion else []
        return tramos + [{'nombre': pantalla, 'url': None}]

    pantallas = _pantallas_del_menu()

    # 2. La pantalla está en el menú: coincidencia exacta del nombre de URL.
    for url_menu, ruta, seccion, pantalla in pantallas:
        if url_menu == nombre_url:
            return [
                {'nombre': seccion, 'url': None},
                {'nombre': pantalla, 'url': None},
            ]

    # 3. Subpáginas (por ejemplo /remitos/5/pdf/): la pantalla del menú
    #    cuya dirección es el comienzo de la actual. Gana la más larga.
    candidatas = [
        p for p in pantallas
        if p[1] and p[1] != '/' and request.path.startswith(p[1])
    ]

    if candidatas:
        url_menu, ruta, seccion, pantalla = max(candidatas, key=lambda p: len(p[1]))
        return [
            {'nombre': seccion, 'url': None},
            {'nombre': pantalla, 'url': ruta},
        ]

    return []


# ------------------------------------------------------------
# FECHA EN ESPAÑOL
# No depende de LANGUAGE_CODE (que en settings está en inglés).
# ------------------------------------------------------------

MESES = (
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
)


def _fecha_de_hoy():
    """Ej.: '2 de noviembre de 2026'."""
    hoy = timezone.localdate()
    return f'{hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}'


# ------------------------------------------------------------
# CAMPANA DE ALERTAS
# Solo aparece si el perfil puede ver el historial de alertas.
# ------------------------------------------------------------

def _datos_alertas(usuario):
    """Devuelve (puede_ver, url, pendientes)."""

    if not puede(usuario, 'alertas'):
        return False, '', 0

    from .models import Alertas

    return (
        True,
        reverse('historial_alertas'),
        Alertas.objects.filter(Atendida=False).count(),
    )


def configuracion_sesion(request):
    sesion = getattr(request, 'session', None)

    if not sesion or not sesion.get('usuario_id'):
        return {}

    from .views import usuario_autenticado

    usuario = usuario_autenticado(request)

    if not usuario:
        return {}

    puede_alertas, url_alertas, alertas_pendientes = _datos_alertas(usuario)

    return {
        'inactividad_ms': settings.INACTIVIDAD_SEGUNDOS * 1000,
        'rutas_denegadas': rutas_denegadas(usuario),
        'perm': permisos_ui(usuario),
        'topbar_ubicacion': _ubicacion(request),
        'topbar_fecha': _fecha_de_hoy(),
        'puede_ver_alertas': puede_alertas,
        'url_alertas': url_alertas,
        'alertas_pendientes': alertas_pendientes,
    }