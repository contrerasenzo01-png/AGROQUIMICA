"""
Notificaciones y configuración de reglas · Agroquímica del Valle

  - CONFIGURACIÓN: los umbrales de las reglas de alertas se guardan en la
    tabla CONFIGURACION (no están fijos en el código). Si falta una clave,
    se crea con su valor por defecto la primera vez que se lee.

  - NOTIFICACIONES: cada regla que se cumple deja una notificación en la
    tabla NOTIFICACION para cada perfil destinatario. El usuario las ve en
    la bandeja del header (con el número de no leídas) y en la pantalla
    "Notificaciones".

  - SIN DUPLICADOS: cada notificación lleva una "Clave" que identifica el
    evento que la disparó (ej. 'stock:15' = alerta de stock Nº 15). La base
    tiene una restricción única (Clave, Destino_perfil), así que aunque la
    regla se evalúe dos veces (dos pestañas, el job diario y la revisión en
    línea a la vez) el mismo evento se notifica una sola vez.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Configuracion, Notificacion, Perfiles
from .permissions import MODULOS, PERFILES_ADMIN

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# CONFIGURACIÓN
# clave -> (valor por defecto, mínimo, máximo, título, descripción)
# ------------------------------------------------------------

PARAMETROS = {
    'dias_aviso_vencimiento': (
        30, 1, 365,
        'Días de aviso de vencimiento',
        'Se avisa cuando a un lote con stock le faltan estos días o menos para vencer.',
    ),
    'margen_stock_minimo': (
        0, 0, 100,
        'Margen sobre el stock mínimo (%)',
        'Se avisa cuando el stock llega al mínimo más este porcentaje. '
        'Con 0 se avisa recién al llegar al mínimo.',
    ),
    'egreso_inusual_desvios': (
        3, 1, 10,
        'Egreso inusual: desvíos estándar',
        'Un egreso es inusual si supera la media de egresos del producto '
        'en esta cantidad de desvíos estándar (regla de 3σ).',
    ),
    'egreso_inusual_min_muestras': (
        5, 2, 1000,
        'Egreso inusual: egresos previos mínimos',
        'Cantidad mínima de egresos anteriores del producto para poder '
        'calcular la media y el desvío.',
    ),
    'minutos_revision_vencimientos': (
        10, 1, 1440,
        'Revisión automática de vencimientos (minutos)',
        'Cada cuántos minutos se revisan los vencimientos mientras alguien '
        'usa el sistema (además del job diario).',
    ),
    'correo_alertas_activo': (
        1, 0, 1,
        'Enviar correos de alertas (1 = sí, 0 = no)',
        'Si está en 1, las alertas también se envían por correo electrónico.',
    ),
}


def asegurar_configuracion():
    """Crea las claves que falten con su valor por defecto."""
    existentes = set(Configuracion.objects.values_list('Clave', flat=True))

    for clave, (defecto, _mn, _mx, titulo, descripcion) in PARAMETROS.items():
        if clave not in existentes:
            try:
                Configuracion.objects.create(
                    Clave=clave,
                    Valor=str(defecto),
                    Descripcion=f'{titulo}. {descripcion}'[:255],
                )
            except IntegrityError:
                pass   # otra petición la creó al mismo tiempo


def config(clave):
    """Valor entero de un parámetro (el de la tabla, o el por defecto)."""
    defecto, minimo, maximo = PARAMETROS[clave][:3]

    valor = Configuracion.objects.filter(Clave=clave).values_list(
        'Valor', flat=True
    ).first()

    if valor is None:
        asegurar_configuracion()
        return defecto

    try:
        return min(max(int(valor), minimo), maximo)
    except (TypeError, ValueError):
        return defecto


# ------------------------------------------------------------
# DESTINATARIOS
# ------------------------------------------------------------

def perfiles_con_permiso(modulo):
    """Perfiles activos que pueden ver un módulo (el Administrador siempre)."""
    consultar, gestionar = MODULOS[modulo]
    nombres = {n.lower() for n in (consultar, gestionar) if n}

    perfiles = []

    for perfil in Perfiles.objects.filter(Estado_perfil=True).prefetch_related('permisos'):
        if perfil.Nombre_perfil in PERFILES_ADMIN:
            perfiles.append(perfil)
            continue

        asignados = {p.Nombre_permiso.strip().lower() for p in perfil.permisos.all()}

        if asignados & nombres:
            perfiles.append(perfil)

    return perfiles


def perfiles_admin():
    return list(Perfiles.objects.filter(
        Estado_perfil=True, Nombre_perfil__in=PERFILES_ADMIN
    ))


# ------------------------------------------------------------
# CREAR NOTIFICACIONES
# ------------------------------------------------------------

def notificar(tipo, mensaje, clave, perfiles):
    """Deja una notificación por perfil. Devuelve cuántas se crearon.

    Si ya existe una notificación con esa clave para el perfil, no se
    repite (ver la restricción única del modelo).
    """
    creadas = 0

    for perfil in perfiles:
        try:
            with transaction.atomic():
                _, nueva = Notificacion.objects.get_or_create(
                    Clave=clave[:100],
                    Destino_perfil=perfil,
                    defaults={'Tipo': tipo[:50], 'Mensaje': mensaje[:255]},
                )
            creadas += int(nueva)
        except IntegrityError:
            pass   # se creó al mismo tiempo desde otra petición

    return creadas


# ------------------------------------------------------------
# BANDEJA
# ------------------------------------------------------------

# Tipo de notificación -> clase del ícono en la bandeja
CLASES_TIPO = {
    'Stock mínimo': 'stock',
    'Vencimiento': 'vencimiento',
    'Egreso inusual': 'inusual',
}


def notificaciones_de(usuario):
    """Notificaciones dirigidas al perfil del usuario."""
    if not usuario or not usuario.ID_Perfil_id:
        return Notificacion.objects.none()

    return Notificacion.objects.filter(Destino_perfil_id=usuario.ID_Perfil_id)


def no_leidas(usuario):
    return notificaciones_de(usuario).filter(Leida=False).count()


def _hace(fecha):
    """'recién', 'hace 5 min', 'hace 3 h', 'ayer', 'hace 4 días'."""
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
    return 'ayer' if dias == 1 else f'hace {dias} días'


def datos_bandeja(usuario, limite=15):
    """JSON para la bandeja del header: primero las no leídas."""
    lista = notificaciones_de(usuario).order_by('Leida', '-Fecha')[:limite]

    return {
        'no_leidas': no_leidas(usuario),
        'notificaciones': [
            {
                'id': n.ID_Notificacion,
                'tipo': CLASES_TIPO.get(n.Tipo, 'stock'),
                'etiqueta': n.Tipo,
                'mensaje': n.Mensaje,
                'hace': _hace(n.Fecha),
                'leida': n.Leida,
            }
            for n in lista
        ],
    }


def marcar_leida(usuario, notificacion):
    if notificacion.Leida:
        return False

    notificacion.Leida = True
    notificacion.Fecha_lectura = timezone.now()
    notificacion.save(update_fields=['Leida', 'Fecha_lectura'])
    return True


def marcar_todas_leidas(usuario):
    return notificaciones_de(usuario).filter(Leida=False).update(
        Leida=True,
        Fecha_lectura=timezone.now(),
    )

