import time
from urllib.parse import quote, urlparse

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

RUTAS_LIBRES = {
    '/', '/login/', '/cerrar-sesion/', '/bloqueo/', '/bloqueo/registrar/',
}

class SesionInactivaMiddleware:
    """Bloquea la sesión si pasaron más de INACTIVIDAD_SEGUNDOS sin actividad."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.session.get('usuario_id'):
            return self.get_response(request)

        if (
            request.path in RUTAS_LIBRES
            or request.path.startswith(settings.STATIC_URL)
        ):
            return self.get_response(request)

        ahora = time.time()
        ultima = request.session.get('ultima_actividad', ahora)

        if (
            request.session.get('bloqueada')
            or ahora - ultima > settings.INACTIVIDAD_SEGUNDOS
        ):
            request.session['bloqueada'] = True

            if self._es_ajax(request):
                return JsonResponse({'bloqueada': True}, status=401)

            return redirect(
                f"{reverse('bloqueo')}?next="
                f"{quote(self._destino(request), safe='')}"
            )

        request.session['ultima_actividad'] = ahora

        return self.get_response(request)

    @staticmethod
    def _es_ajax(request):
        return (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('Accept', '')
        )

    @staticmethod
    def _destino(request):
        if request.method == 'GET':
            return request.get_full_path()

        referer = request.META.get('HTTP_REFERER', '')

        if referer and url_has_allowed_host_and_scheme(
            referer, allowed_hosts={request.get_host()}
        ):
            p = urlparse(referer)
            return p.path + (f'?{p.query}' if p.query else '')

        return reverse('panel_principal')

class VolverAlModuloMiddleware:
    """
    Si un usuario logueado hace una acción (POST) sin tener el permiso,
    en lugar de mandarlo al panel principal lo devuelve a la pantalla
    donde estaba, con un mensaje de error.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method != 'POST':
            return response

        if not getattr(request, 'permiso_denegado', False):
            return response

        if response.status_code not in (301, 302):
            return response

        if response.get('Location') != reverse('panel_principal'):
            return response

        referer = request.META.get('HTTP_REFERER', '')

        if not referer or not url_has_allowed_host_and_scheme(
            referer, allowed_hosts={request.get_host()}
        ):
            return response

        ruta = urlparse(referer).path

        if ruta in (request.path, reverse('panel_principal')):
            return response

        # Si la vista no dejó ya un mensaje de error, agrega uno genérico.
        almacen = getattr(request, '_messages', None)

        if almacen is not None and not getattr(almacen, '_queued_messages', []):
            messages.error(
                request,
                'No tiene permiso para realizar esta acción.'
            )

        response['Location'] = referer

        return response