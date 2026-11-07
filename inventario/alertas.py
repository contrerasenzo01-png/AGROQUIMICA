"""
Alertas del sistema · Agroquímica del Valle

Toda la lógica de alertas está acá, así se genera igual
desde cualquier pantalla:

  - STOCK MÍNIMO: cuando el stock de un producto queda en su
    stock mínimo o por debajo. Se revisa cada vez que el stock baja
    (egreso, anulación de remito, corrección de lote) y cuando se
    cambia el stock mínimo de un producto.
    El correo le llega al usuario que hizo ese movimiento.

  - VENCIMIENTO: cuando a un lote con stock le faltan
    DIAS_AVISO_VENCIMIENTO días o menos para vencer (o ya venció).
    Se revisa sola, como mucho una vez cada 10 minutos, mientras
    alguien usa el sistema.
    El correo les llega a todos los usuarios que pueden ver alertas.

Cada alerta se envía por correo una sola vez: cuando se crea.
"""

import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.console import EmailBackend as CorreoConsola
from django.core.mail.backends.smtp import EmailBackend as CorreoSMTP
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Alertas, Lotes, Stock, Usuarios
from .permissions import puede

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# REGLAS
# ------------------------------------------------------------

DIAS_AVISO_VENCIMIENTO = 30

TIPO_STOCK = 'Stock mínimo'
TIPO_VENCIMIENTO = 'Vencimiento'

# Las alertas viejas de stock se guardaban como "Stock bajo".
TIPOS_STOCK = (TIPO_STOCK, 'Stock bajo')

# Cada cuánto se revisan solos los vencimientos (en segundos).
REVISION_VENCIMIENTOS_SEGUNDOS = 10 * 60


# ------------------------------------------------------------
# CORREO
# Los datos de la cuenta de Gmail están en settings.CORREO_ALERTAS
# (y estos, en el archivo .env). Si no están cargados, los correos
# se muestran en la terminal en lugar de enviarse.
# ------------------------------------------------------------

def _config_correo():
    return getattr(settings, 'CORREO_ALERTAS', {}) or {}


def _conexion_correo():
    config = _config_correo()

    if config.get('usuario') and config.get('contrasena'):
        return CorreoSMTP(
            host=config.get('host', 'smtp.gmail.com'),
            port=config.get('puerto', 587),
            username=config['usuario'],
            password=config['contrasena'],
            use_tls=True,
            timeout=20,
        )

    # Sin cuenta configurada: el correo se imprime en la terminal.
    return CorreoConsola()


def _remitente():
    cuenta = _config_correo().get('usuario') or 'alertas@agroquimica.local'
    return f'Agroquímica del Valle <{cuenta}>'


def _enviar_correo(asunto, texto, html, destinatarios):
    """Envía el correo en segundo plano, después de guardar los cambios.

    Va en copia oculta, así cada usuario no ve los correos de los demás.
    Si el envío falla, queda registrado en la terminal pero no corta
    la operación que disparó la alerta.
    """

    destinatarios = sorted({
        d.strip() for d in destinatarios if d and d.strip()
    })

    if not destinatarios:
        return

    remitente = _remitente()

    def tarea():
        try:
            correo = EmailMultiAlternatives(
                subject=asunto,
                body=texto,
                from_email=remitente,
                to=[remitente],
                bcc=destinatarios,
                connection=_conexion_correo(),
            )
            correo.attach_alternative(html, 'text/html')
            correo.send()
        except Exception:
            logger.exception('No se pudo enviar el correo de alerta "%s".', asunto)

    # Recién cuando la operación se guardó en la base, y sin hacer
    # esperar al usuario mientras se conecta con Gmail.
    transaction.on_commit(
        lambda: threading.Thread(target=tarea, daemon=True).start()
    )


def _correo_alerta(asunto, titulo, introduccion, filas, color):
    """Arma el texto y el HTML del correo con el diseño de la agroquímica."""

    sitio = getattr(settings, 'SITIO_URL', '').rstrip('/')

    datos = {
        'titulo': titulo,
        'introduccion': introduccion,
        'filas': filas,
        'color': color,
        'enlace': f'{sitio}/historial-alertas/' if sitio else '',
        'fecha': timezone.localtime().strftime('%d/%m/%Y %H:%M'),
    }

    texto = '\n'.join(
        [titulo, '', introduccion, '']
        + [' · '.join(str(v) for v in fila) for fila in filas]
        + ['', 'Agroquímica del Valle · Sistema de Gestión de Stock']
    )

    html = render_to_string('inventario/correo_alerta.html', datos)

    return asunto, texto, html


def destinatarios_alertas():
    """Correos de los usuarios activos cuyo perfil puede ver alertas."""

    usuarios = Usuarios.objects.select_related('ID_Perfil').filter(
        Estado_usuario=True,
        ID_Perfil__Estado_perfil=True,
    ).exclude(Email_usuario='').exclude(Email_usuario__isnull=True)

    return [u.Email_usuario for u in usuarios if puede(u, 'alertas')]


# ------------------------------------------------------------
# ALERTAS DE STOCK MÍNIMO
# ------------------------------------------------------------

def revisar_stock(stock, usuario=None):
    """Genera la alerta si el stock quedó en el mínimo o por debajo.

    Devuelve True si el producto está en o bajo el mínimo (haya
    creado una alerta nueva o ya hubiera una pendiente).
    """

    if stock is None or stock.Cantidad_stock > stock.Stock_minimo:
        return False

    # Si ya hay una alerta de stock pendiente, no se repite.
    if Alertas.objects.filter(
        ID_Stock=stock,
        Tipo_alerta__in=TIPOS_STOCK,
        Atendida=False,
    ).exists():
        return True

    producto = stock.ID_Producto

    Alertas.objects.create(
        ID_Stock=stock,
        Tipo_alerta=TIPO_STOCK,
        Mensaje=(
            f'El producto {producto.Nombre_producto} quedó con '
            f'{stock.Cantidad_stock} unidades '
            f'(stock mínimo: {stock.Stock_minimo}).'
        )[:255],
        Cantidad_al_generar=stock.Cantidad_stock,
        Stock_minimo_al_generar=stock.Stock_minimo,
        Atendida=False,
    )

    # Correo al usuario que hizo el movimiento.
    if usuario and usuario.Email_usuario:
        sin_stock = stock.Cantidad_stock <= 0

        asunto, texto, html = _correo_alerta(
            asunto=(
                f'{"Sin stock" if sin_stock else "Stock mínimo"}: '
                f'{producto.Nombre_producto}'
            ),
            titulo=(
                'Producto sin stock' if sin_stock
                else 'Producto en stock mínimo'
            ),
            introduccion=(
                f'Estimado/a {usuario.Nombre_usuario}: le informamos que, después del movimiento que '
                f'usted registró, el producto quedó en su stock mínimo o por debajo.'
            ),
            filas=[
                ('Producto', producto.Nombre_producto),
                ('Stock actual', f'{stock.Cantidad_stock} unidades'),
                ('Stock mínimo', f'{stock.Stock_minimo} unidades'),
            ],
            color='#b91c1c',
        )

        _enviar_correo(asunto, texto, html, [usuario.Email_usuario])

    return True


# ------------------------------------------------------------
# ALERTAS DE VENCIMIENTO
# ------------------------------------------------------------

def _texto_vencimiento(lote, dias):
    if dias < 0:
        return f'está vencido desde el {lote.Fecha_vencimiento:%d/%m/%Y}.'
    if dias == 0:
        return f'vence hoy ({lote.Fecha_vencimiento:%d/%m/%Y}).'
    if dias == 1:
        return f'vence mañana ({lote.Fecha_vencimiento:%d/%m/%Y}).'
    return f'vence en {dias} días ({lote.Fecha_vencimiento:%d/%m/%Y}).'


def revisar_vencimientos():
    """Crea o actualiza las alertas de los lotes que vencen pronto.

    Devuelve la lista de lotes por vencer (o vencidos con stock),
    con el mismo formato que usaba antes generar_alertas_vencimiento
    en views.py, así el panel principal no cambia.
    """

    hoy = timezone.localdate()
    limite = hoy + timedelta(days=DIAS_AVISO_VENCIMIENTO)

    lotes = Lotes.objects.select_related('ID_Producto').filter(
        Fecha_vencimiento__isnull=False,
        Fecha_vencimiento__lte=limite,
        Cantidad_actual__gt=0,
    ).order_by('Fecha_vencimiento')

    resultado = []
    nuevas = []

    for lote in lotes:
        dias = (lote.Fecha_vencimiento - hoy).days
        producto = lote.ID_Producto
        texto = _texto_vencimiento(lote, dias)

        mensaje = (
            f'El producto {producto.Nombre_producto} '
            f'del lote {lote.Numero_lote} {texto}'
        )

        stock = Stock.objects.filter(ID_Producto=producto).first()

        if stock:
            # El marcador permite saber de qué lote es cada alerta.
            mensaje_guardado = f'{mensaje} [LOTE_ID:{lote.ID_Lote}]'[:255]

            alerta = Alertas.objects.filter(
                ID_Stock=stock,
                Tipo_alerta=TIPO_VENCIMIENTO,
                Mensaje__contains=f'[LOTE_ID:{lote.ID_Lote}]',
            ).order_by('ID_Historial_alerta').first()

            if alerta:
                # Se actualiza el texto (los días restantes cambian)
                # sin tocar la fecha de creación ni si fue atendida.
                if alerta.Mensaje != mensaje_guardado:
                    alerta.Mensaje = mensaje_guardado
                    alerta.save(update_fields=['Mensaje'])
            else:
                Alertas.objects.create(
                    ID_Stock=stock,
                    Tipo_alerta=TIPO_VENCIMIENTO,
                    Mensaje=mensaje_guardado,
                    Cantidad_al_generar=lote.Cantidad_actual,
                    Stock_minimo_al_generar=stock.Stock_minimo,
                    Atendida=False,
                )
                nuevas.append((lote, dias))

        resultado.append({
            'producto': producto,
            'lote': lote,
            'dias_restantes': dias,
            'mensaje': mensaje,
        })

    # Un solo correo con todas las alertas nuevas, a quienes ven alertas.
    if nuevas:
        cantidad = len(nuevas)

        asunto, texto, html = _correo_alerta(
            asunto=(
                f'Vencimiento: {nuevas[0][0].ID_Producto.Nombre_producto}'
                if cantidad == 1
                else f'Vencimiento: {cantidad} lotes por vencer'
            ),
            titulo=(
                'Lote próximo a vencer' if cantidad == 1
                else f'{cantidad} lotes próximos a vencer'
            ),
            introduccion=(
                f'Le informamos que los siguientes lotes vencen en los próximos '
                f'{DIAS_AVISO_VENCIMIENTO} días y todavía tienen stock.'
            ),
            filas=[
                (
                    lote.ID_Producto.Nombre_producto,
                    f'Lote {lote.Numero_lote} · {lote.Cantidad_actual} un.',
                    _texto_vencimiento(lote, dias).rstrip('.').capitalize(),
                )
                for lote, dias in nuevas
            ],
            color='#b45309',
        )

        _enviar_correo(asunto, texto, html, destinatarios_alertas())

    return resultado


def revisar_vencimientos_si_corresponde():
    """Revisa los vencimientos como mucho una vez cada 10 minutos.

    La llama context_processors.py en cada página, así el número
    de alertas del topbar siempre está al día.
    """

    if cache.add('alertas:revision_vencimientos', True, REVISION_VENCIMIENTOS_SEGUNDOS):
        try:
            revisar_vencimientos()
        except Exception:
            # Si falla, se reintenta en la próxima página.
            cache.delete('alertas:revision_vencimientos')
            logger.exception('No se pudieron revisar los vencimientos.')


# ------------------------------------------------------------
# BANDEJA DE NOTIFICACIONES (topbar)
# ------------------------------------------------------------

def _hace(fecha):
    """'hace 5 min', 'hace 3 h', 'ayer', 'hace 4 días'."""

    if not fecha:
        return ''

    segundos = int((timezone.now() - fecha).total_seconds())

    if segundos < 60:
        return 'recién'
    if segundos < 3600:
        return f'hace {segundos // 60} min'
    if segundos < 86400:
        return f'hace {segundos // 3600} h'

    dias = segundos // 86400

    if dias == 1:
        return 'ayer'

    return f'hace {dias} días'


def mensaje_visible(mensaje):
    """Quita el marcador técnico [LOTE_ID:...] del mensaje."""
    return (mensaje or '').split(' [LOTE_ID:', 1)[0]


def listar_notificaciones(limite=15):
    """Alertas pendientes para la bandeja del topbar."""

    pendientes = Alertas.objects.filter(Atendida=False)

    alertas = pendientes.select_related(
        'ID_Stock__ID_Producto'
    ).order_by('-Fecha_hora_historial_alerta')[:limite]

    lista = []

    for alerta in alertas:
        es_stock = alerta.Tipo_alerta in TIPOS_STOCK
        mensaje = mensaje_visible(alerta.Mensaje)

        lista.append({
            'id': alerta.ID_Historial_alerta,
            'tipo': 'stock' if es_stock else 'vencimiento',
            'etiqueta': TIPO_STOCK if es_stock else TIPO_VENCIMIENTO,
            'vencido': 'vencido' in mensaje.lower(),
            'producto': alerta.ID_Stock.ID_Producto.Nombre_producto,
            'mensaje': mensaje,
            'hace': _hace(alerta.Fecha_hora_historial_alerta),
        })

    return {
        'pendientes': pendientes.count(),
        'alertas': lista,
    }