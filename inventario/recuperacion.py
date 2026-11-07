"""
Recuperación de contraseña por correo.

- El enlace lleva un token firmado (no se guarda nada en la base).
- Vence según settings.PASSWORD_RESET_TIMEOUT (1 hora).
- Es de un solo uso: el token incluye el hash de la contraseña actual,
  así que en cuanto se cambia la contraseña deja de servir.
- Máximo 3 pedidos por hora por correo y por IP.
"""

import hashlib
import logging
import threading

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .alertas import _conexion_correo, _remitente
from .models import Usuarios

logger = logging.getLogger(__name__)

LIMITE_PEDIDOS = 3
VENTANA_SEGUNDOS = 60 * 60


class TokenRecuperacion(PasswordResetTokenGenerator):
    key_salt = 'inventario.recuperacion.TokenRecuperacion'

    def _make_hash_value(self, usuario, timestamp):
        # Si cambia la contraseña, el correo o el estado, el enlace muere.
        return (
            f'{usuario.pk}{usuario.Contrasena}{usuario.Email_usuario}'
            f'{usuario.Estado_usuario}{timestamp}'
        )


generador_token = TokenRecuperacion()


def usuario_desde_uid(uidb64):
    try:
        pk = force_str(urlsafe_base64_decode(uidb64))
        return Usuarios.objects.select_related('ID_Perfil').get(pk=pk)
    except (TypeError, ValueError, OverflowError, Usuarios.DoesNotExist):
        return None


def token_valido(usuario, token):
    return generador_token.check_token(usuario, token)


def usuario_habilitado(usuario):
    return bool(
        usuario
        and usuario.Estado_usuario
        and usuario.ID_Perfil
        and usuario.ID_Perfil.Estado_perfil
    )


# ------------------------------------------------------------
# LÍMITE DE PEDIDOS
# ------------------------------------------------------------

def _contar(clave):
    if cache.add(clave, 1, VENTANA_SEGUNDOS):
        return 1

    try:
        return cache.incr(clave)
    except ValueError:
        cache.set(clave, 1, VENTANA_SEGUNDOS)
        return 1


def _ip(request):
    return (
        request.META.get('HTTP_CF_CONNECTING_IP')
        or request.META.get('REMOTE_ADDR', '')
    )


def limite_superado(request, email):
    huella = hashlib.sha256(email.strip().lower().encode()).hexdigest()

    por_ip = _contar(f'recuperacion:ip:{_ip(request)}')
    por_correo = _contar(f'recuperacion:mail:{huella}')

    return por_ip > LIMITE_PEDIDOS or por_correo > LIMITE_PEDIDOS


# ------------------------------------------------------------
# CORREO
# ------------------------------------------------------------

def enlace_recuperacion(usuario):
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = generador_token.make_token(usuario)
    sitio = getattr(settings, 'SITIO_URL', '').rstrip('/')

    return sitio + reverse('recuperar_confirmar', args=[uid, token])


def enviar_correo_recuperacion(usuario):
    """Envía el enlace en segundo plano, así la respuesta tarda lo mismo
    exista o no el correo."""

    enlace = enlace_recuperacion(usuario)
    minutos = int(getattr(settings, 'PASSWORD_RESET_TIMEOUT', 3600)) // 60

    datos = {
        'nombre': usuario.Nombre_usuario,
        'usuario': usuario.Usuario,
        'enlace': enlace,
        'minutos': minutos,
        'fecha': timezone.localtime().strftime('%d/%m/%Y %H:%M'),
    }

    texto = (
        f'Hola {usuario.Nombre_usuario}:\n\n'
        f'Hemos recibido una solicitud para restablecer la contraseña de su usuario '
        f'"{usuario.Usuario}".\n\n'
        f'Ingrese al siguiente enlace para crear una nueva (vence en {minutos} minutos):\n'
        f'{enlace}\n\n'
        f'Si usted no realizó esta solicitud, puede ignorar este correo: su contraseña no será modificada.\n\n'
        f'Agroquímica del Valle · Sistema de Gestión de Stock'
    )

    html = render_to_string('inventario/correo_recuperacion.html', datos)

    remitente = _remitente()
    destino = usuario.Email_usuario

    def tarea():
        try:
            correo = EmailMultiAlternatives(
                subject='Restablecer su contraseña · Agroquímica del Valle',
                body=texto,
                from_email=remitente,
                to=[destino],
                connection=_conexion_correo(),
            )
            correo.attach_alternative(html, 'text/html')
            correo.send()
        except Exception:
            logger.exception('No se pudo enviar el correo de recuperación.')

    threading.Thread(target=tarea, daemon=True).start()