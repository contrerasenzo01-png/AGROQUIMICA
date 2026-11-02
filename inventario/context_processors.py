from django.conf import settings

from .permissions import permisos_ui, rutas_denegadas


# ------------------------------------------------------------
# UBICACIÓN ACTUAL (la barra superior la muestra en vez del
# nombre de la empresa). Se detecta por palabras de la URL y
# usa los mismos nombres que el menú lateral.
# El orden importa: "subtipo" va antes que "tipo", etc.
# ------------------------------------------------------------

SECCIONES = [
    ('movimiento', 'Inventario', 'Movimientos de stock'),
    ('subtipo', 'Inventario', 'Subtipos'),
    ('tipo', 'Inventario', 'Tipos de productos'),
    ('proveedor', 'Inventario', 'Proveedores'),
    ('remito', 'Inventario', 'Remitos'),
    ('lote', 'Inventario', 'Lotes'),
    ('producto', 'Inventario', 'Productos y stock'),
    ('stock', 'Inventario', 'Productos y stock'),
    ('alerta', 'Inventario', 'Historial de alertas'),
    ('reporte', 'Inventario', 'Reportes'),
    ('usuario', 'Administración', 'Usuarios del sistema'),
    ('auditor', 'Administración', 'Auditoría'),
]


def _ubicacion(request):
    """Lista de tramos [{'nombre': ..., 'url': ...}] para la barra superior."""

    match = getattr(request, 'resolver_match', None)
    nombre_url = (match.url_name or '') if match else ''
    referencia = f'{nombre_url} {request.path}'.lower()

    if request.path.strip('/') == '' or any(
        palabra in nombre_url.lower()
        for palabra in ('panel', 'dashboard', 'inicio', 'home')
    ):
        return [{'nombre': 'Panel principal', 'url': None}]

    for palabra, grupo, pantalla in SECCIONES:
        if palabra in referencia:
            return [
                {'nombre': grupo, 'url': None},
                {'nombre': pantalla, 'url': None},
            ]

    if nombre_url:
        return [{'nombre': nombre_url.replace('_', ' ').capitalize(), 'url': None}]

    return []


# ------------------------------------------------------------
# CAMPANA DE ALERTAS
# Mientras esta función devuelva (False, '', 0) la campana no se
# muestra. Para activarla hay que devolver:
#   puede_ver : True si el perfil tiene permiso para ver alertas
#   url       : reverse('nombre_de_la_url_de_alertas')
#   pendientes: cantidad de alertas sin atender
# ------------------------------------------------------------

def _datos_alertas(usuario, perm):
    return False, '', 0


def configuracion_sesion(request):
    sesion = getattr(request, 'session', None)

    if not sesion or not sesion.get('usuario_id'):
        return {}

    from .views import usuario_autenticado

    usuario = usuario_autenticado(request)

    if not usuario:
        return {}

    perm = permisos_ui(usuario)
    puede_alertas, url_alertas, alertas_pendientes = _datos_alertas(usuario, perm)

    return {
        'inactividad_ms': settings.INACTIVIDAD_SEGUNDOS * 1000,
        'rutas_denegadas': rutas_denegadas(usuario),
        'perm': perm,
        'topbar_ubicacion': _ubicacion(request),
        'puede_ver_alertas': puede_alertas,
        'url_alertas': url_alertas,
        'alertas_pendientes': alertas_pendientes,
    }