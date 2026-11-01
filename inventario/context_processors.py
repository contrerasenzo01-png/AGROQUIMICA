from django.conf import settings

from .permissions import permisos_ui, rutas_denegadas


def configuracion_sesion(request):
    sesion = getattr(request, 'session', None)

    if not sesion or not sesion.get('usuario_id'):
        return {}

    from .views import usuario_autenticado

    usuario = usuario_autenticado(request)

    if not usuario:
        return {}

    return {
        'inactividad_ms': settings.INACTIVIDAD_SEGUNDOS * 1000,
        'rutas_denegadas': rutas_denegadas(usuario),
        'perm': permisos_ui(usuario),
    }