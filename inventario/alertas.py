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
    "dias_aviso_vencimiento" días o menos para vencer (o ya venció).
    Se revisa sola mientras alguien usa el sistema (cada
    "minutos_revision_vencimientos") y con el job diario
    `python manage.py revisar_alertas`.
    El correo les llega a todos los usuarios que pueden ver alertas.

  - EGRESO INUSUAL: cuando un egreso por venta supera la media de los
    egresos anteriores del producto en "egreso_inusual_desvios" desvíos
    estándar (regla de 3σ). Se evalúa en tiempo real al registrar el
    egreso. Se notifica al Administrador (bandeja y correo).

Los umbrales entre comillas se leen de la tabla CONFIGURACION
(ver notificaciones.py). Cada regla deja además una notificación en la
tabla NOTIFICACION para los perfiles destinatarios.

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

from .models import Alertas, Lotes, MovimientosStock, Stock, Usuarios
from .notificaciones import config, notificar, perfiles_admin, perfiles_con_permiso
from .permissions import PERFILES_ADMIN, puede

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# REGLAS
# ------------------------------------------------------------

TIPO_STOCK = 'Stock mínimo'
TIPO_VENCIMIENTO = 'Vencimiento'
TIPO_INUSUAL = 'Egreso inusual'

# Tipos de movimiento que cuentan como venta (el segundo es el nombre viejo).
TIPOS_VENTA = ('Egreso por venta', 'Salida por venta')

# Las alertas viejas de stock se guardaban como "Stock bajo".
TIPOS_STOCK = (TIPO_STOCK, 'Stock bajo')


# ------------------------------------------------------------
# CORREO
# Los datos de la cuenta de Gmail están en settings.CORREO_ALERTAS
# (y estos, en el archivo .env). Si no están cargados, los correos
# se muestran en la terminal en lugar de enviarse.
# ------------------------------------------------------------

# Hilos de envío en curso. El servidor no los necesita, pero el job
# diario (manage.py revisar_alertas) termina enseguida y, si no los
# espera, corta los correos antes de que salgan (ver esperar_correos).
_hilos_correo = []
_hilos_lock = threading.Lock()


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

    if not config('correo_alertas_activo'):
        return

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

    def lanzar():
        hilo = threading.Thread(target=tarea, daemon=True)
        with _hilos_lock:
            # Se descartan los que ya terminaron, así la lista no crece.
            _hilos_correo[:] = [h for h in _hilos_correo if h.is_alive()]
            _hilos_correo.append(hilo)
        hilo.start()

    # Recién cuando la operación se guardó en la base, y sin hacer
    # esperar al usuario mientras se conecta con Gmail.
    transaction.on_commit(lanzar)


def esperar_correos(segundos=30):
    """Espera a que terminen los correos en curso.

    La llama el job diario antes de terminar: los hilos son "daemon" y
    se cortarían al cerrarse el proceso, sin llegar a enviar el correo.
    """
    with _hilos_lock:
        hilos = list(_hilos_correo)

    for hilo in hilos:
        hilo.join(segundos)

    return len(hilos)


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


def correos_administradores():
    """Correos de los usuarios activos con perfil Administrador."""
    return list(Usuarios.objects.filter(
        Estado_usuario=True,
        ID_Perfil__Estado_perfil=True,
        ID_Perfil__Nombre_perfil__in=PERFILES_ADMIN,
    ).exclude(Email_usuario='').exclude(Email_usuario__isnull=True).values_list(
        'Email_usuario', flat=True
    ))


# ------------------------------------------------------------
# ALERTAS DE STOCK MÍNIMO
# ------------------------------------------------------------

def umbral_stock(stock):
    """Stock a partir del cual se avisa: el mínimo más el margen configurado."""
    margen = config('margen_stock_minimo')
    return stock.Stock_minimo + (stock.Stock_minimo * margen + 99) // 100


def revisar_stock(stock, usuario=None):
    """Genera la alerta si el stock quedó en el umbral o por debajo.

    El umbral es el stock mínimo del producto más el margen de la
    configuración (con margen 0, el stock mínimo).
    Devuelve True si el producto está en o bajo el umbral (haya
    creado una alerta nueva o ya hubiera una pendiente).
    """

    if stock is None or stock.Cantidad_stock > umbral_stock(stock):
        return False

    # Si ya hay una alerta de stock pendiente, no se repite.
    # (Se asegura su notificación: alertas de antes de la bandeja nueva.)
    pendiente = Alertas.objects.filter(
        ID_Stock=stock,
        Tipo_alerta__in=TIPOS_STOCK,
        Atendida=False,
    ).order_by('ID_Historial_alerta').first()

    if pendiente:
        notificar(
            TIPO_STOCK, mensaje_visible(pendiente.Mensaje), f'stock:{pendiente.pk}',
            perfiles_con_permiso('alertas'),
        )
        return True

    producto = stock.ID_Producto

    mensaje = (
        f'El producto {producto.Nombre_producto} quedó con '
        f'{stock.Cantidad_stock} unidades '
        f'(stock mínimo: {stock.Stock_minimo}).'
    )[:255]

    alerta = Alertas.objects.create(
        ID_Stock=stock,
        Tipo_alerta=TIPO_STOCK,
        Mensaje=mensaje,
        Cantidad_al_generar=stock.Cantidad_stock,
        Stock_minimo_al_generar=stock.Stock_minimo,
        Atendida=False,
    )

    # Bandeja: a los perfiles que pueden ver alertas.
    notificar(
        TIPO_STOCK, mensaje, f'stock:{alerta.pk}',
        perfiles_con_permiso('alertas'),
    )

    # Correo: al usuario que hizo el movimiento. Si la alerta la detectó
    # el job diario (sin usuario), a todos los que pueden ver alertas.
    if usuario:
        destinatarios = [usuario.Email_usuario] if usuario.Email_usuario else []
        introduccion = (
            f'Estimado/a {usuario.Nombre_usuario}: le informamos que, después del movimiento que '
            f'usted registró, el producto quedó en su stock mínimo o por debajo.'
        )
    else:
        destinatarios = destinatarios_alertas()
        introduccion = (
            'Le informamos que, en la revisión automática del sistema, el producto '
            'quedó en su stock mínimo o por debajo.'
        )

    if destinatarios:
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
            introduccion=introduccion,
            filas=[
                ('Producto', producto.Nombre_producto),
                ('Stock actual', f'{stock.Cantidad_stock} unidades'),
                ('Stock mínimo', f'{stock.Stock_minimo} unidades'),
            ],
            color='#b91c1c',
        )

        _enviar_correo(asunto, texto, html, destinatarios)

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
    dias_aviso = config('dias_aviso_vencimiento')
    limite = hoy + timedelta(days=dias_aviso)
    destinos = None   # perfiles destinatarios (se buscan una sola vez)

    # Los lotes de remitos anulados no cuentan: su mercadería no está
    # en el depósito aunque el lote conserve una cantidad.
    lotes = Lotes.objects.select_related('ID_Producto').filter(
        Fecha_vencimiento__isnull=False,
        Fecha_vencimiento__lte=limite,
        Cantidad_actual__gt=0,
    ).exclude(
        ID_Remito__Estado_remito='Anulado'
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

                # Alertas pendientes de antes de la bandeja nueva: se
                # notifican una vez (la clave evita repetirlas).
                if not alerta.Atendida:
                    if destinos is None:
                        destinos = perfiles_con_permiso('alertas')
                    notificar(
                        TIPO_VENCIMIENTO, mensaje,
                        f'vencimiento:lote:{lote.ID_Lote}', destinos,
                    )
            else:
                alerta = Alertas.objects.create(
                    ID_Stock=stock,
                    Tipo_alerta=TIPO_VENCIMIENTO,
                    Mensaje=mensaje_guardado,
                    Cantidad_al_generar=lote.Cantidad_actual,
                    Stock_minimo_al_generar=stock.Stock_minimo,
                    Atendida=False,
                )
                nuevas.append((lote, dias))

                if destinos is None:
                    destinos = perfiles_con_permiso('alertas')

                # Clave por lote: el mismo lote no se notifica dos veces.
                notificar(
                    TIPO_VENCIMIENTO, mensaje,
                    f'vencimiento:lote:{lote.ID_Lote}', destinos,
                )

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
                f'{dias_aviso} días y todavía tienen stock.'
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
    """Revisa los vencimientos como mucho una vez cada
    "minutos_revision_vencimientos" (tabla CONFIGURACION).

    La llama context_processors.py en cada página, así el número
    de notificaciones del header siempre está al día.
    """

    segundos = config('minutos_revision_vencimientos') * 60

    if cache.add('alertas:revision_vencimientos', True, segundos):
        try:
            revisar_vencimientos()
        except Exception:
            # Si falla, se reintenta en la próxima página.
            cache.delete('alertas:revision_vencimientos')
            logger.exception('No se pudieron revisar los vencimientos.')


# ------------------------------------------------------------
# EGRESO INUSUAL (regla de 3σ)
# ------------------------------------------------------------

def revisar_egreso_inusual(movimiento):
    """Notifica si un egreso supera media + k·σ de los egresos anteriores.

    Se evalúa en tiempo real, al registrar el egreso. k y la cantidad
    mínima de egresos previos salen de la tabla CONFIGURACION.
    Devuelve True si el egreso resultó inusual.
    """

    if not movimiento or not movimiento.ID_Lote_id:
        return False

    producto = movimiento.ID_Lote.ID_Producto
    k = config('egreso_inusual_desvios')
    minimo_muestras = config('egreso_inusual_min_muestras')

    previos = list(MovimientosStock.objects.filter(
        ID_Lote__ID_Producto=producto,
        ID_Tipo_movimiento__Nombre_tipo_movimiento__in=TIPOS_VENTA,
        Anulado=False,
    ).exclude(pk=movimiento.pk).values_list('Cantidad_movimiento_stock', flat=True))

    if len(previos) < minimo_muestras:
        return False

    media = sum(previos) / len(previos)
    desvio = (sum((x - media) ** 2 for x in previos) / len(previos)) ** 0.5
    # Piso para el desvío: si los egresos previos son todos iguales (σ = 0)
    # o casi, cualquier diferencia mínima sería "inusual". Con el piso, el
    # límite queda al menos en media + k·max(10% de la media, 1 unidad).
    desvio = max(desvio, media * 0.1, 1)
    limite = media + k * desvio
    cantidad = movimiento.Cantidad_movimiento_stock

    if cantidad <= limite:
        return False

    mensaje = (
        f'Egreso inusual de {producto.Nombre_producto}: {cantidad} unidades '
        f'(media {media:.1f}, límite {limite:.1f} = media + {k}σ). '
        f'Registrado por {movimiento.ID_Usuario.Usuario}.'
    )[:255]

    creadas = notificar(
        TIPO_INUSUAL, mensaje, f'egreso:{movimiento.pk}', perfiles_admin()
    )

    if creadas:
        asunto, texto, html = _correo_alerta(
            asunto=f'Egreso inusual: {producto.Nombre_producto}',
            titulo='Egreso de cantidad inusual',
            introduccion=(
                'Se registró un egreso por venta muy superior a lo habitual '
                'para este producto. Verifique que no se trate de un error de carga.'
            ),
            filas=[
                ('Producto', producto.Nombre_producto),
                ('Cantidad egresada', f'{cantidad} unidades'),
                ('Media de egresos', f'{media:.1f} unidades'),
                ('Límite (media + {}σ)'.format(k), f'{limite:.1f} unidades'),
                ('Registrado por', movimiento.ID_Usuario.Usuario),
            ],
            color='#6d28d9',
        )

        _enviar_correo(asunto, texto, html, correos_administradores())

    return True


# ------------------------------------------------------------
# BANDEJA DE ALERTAS (historial viejo, tabla HISTORIAL_ALERTAS)
# La bandeja del header del Parcial 2 usa datos_bandeja() de
# notificaciones.py (tabla NOTIFICACION). Esto queda para la pantalla
# de historial de alertas, si todavía la usa.
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
    """Alertas pendientes del historial (tabla HISTORIAL_ALERTAS)."""

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