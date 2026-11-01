from datetime import date, datetime
from decimal import Decimal

from django.apps import apps

from .models import LogAuditoria

CAMPOS_EXCLUIDOS = {'Contrasena'}   # nunca guardar el hash


def _serializar(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    return valor


def snapshot(obj):
    """Foto de los campos del objeto (las FK quedan como ID)."""
    return {
        f.name: _serializar(getattr(obj, f.attname))
        for f in obj._meta.concrete_fields
        if not f.primary_key and f.name not in CAMPOS_EXCLUIDOS
    }


def nombre_seccion(entidad):
    """
    Unifica el nombre de la sección.
    'USUARIOS', 'usuarios' o 'Usuarios' -> 'Usuarios' (verbose_name_plural del modelo).
    Si no coincide con ningún modelo, se deja como vino.
    """
    if not entidad:
        return entidad

    buscado = entidad.strip().upper()

    for modelo in apps.get_app_config('inventario').get_models():
        meta = modelo._meta
        if buscado in (meta.db_table.upper(), str(meta.verbose_name_plural).upper()):
            return str(meta.verbose_name_plural)

    return entidad.strip()


def registrar_auditoria(usuario, entidad, objeto, accion, antes, despues):
    if accion == 'MODIFICACION' and antes == despues:
        return None

    return LogAuditoria.objects.create(
        ID_Usuario=usuario,
        Seccion=nombre_seccion(entidad),
        ID_Registro=objeto.pk,
        Accion=accion,
        Valores_anteriores=antes,
        Valores_actuales=despues,
    )