from datetime import date, datetime
from decimal import Decimal

from django.apps import apps

from .models import LogAuditoria

CAMPOS_EXCLUIDOS = {'Contrasena','Fecha_ultima_modificacion'}   # nunca guardar el hash


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

def registrar_asignacion_perfil(admin, usuario_obj, perfil_anterior, perfil_nuevo):
    """Quién le asignó qué perfil a un usuario."""
    return LogAuditoria.objects.create(
        ID_Usuario=admin,
        Seccion='Usuarios',
        ID_Registro=usuario_obj.pk,
        Accion='ASIGNACION_PERFIL',
        Valores_anteriores={
            'Perfil': perfil_anterior.Nombre_perfil if perfil_anterior else 'Sin perfil'
        },
        Valores_actuales={
            'Perfil': perfil_nuevo.Nombre_perfil,
            'Usuario': usuario_obj.Usuario,
        },
    )


def registrar_asignacion_permisos(admin, perfil, antes_set, despues_set):
    """Permisos agregados y quitados a un perfil."""
    antes_set, despues_set = set(antes_set), set(despues_set)
    if antes_set == despues_set:
        return None

    return LogAuditoria.objects.create(
        ID_Usuario=admin,
        Seccion='Perfiles',
        ID_Registro=perfil.pk,
        Accion='ASIGNACION_PERMISOS',
        Valores_anteriores={'Permisos': ', '.join(sorted(antes_set)) or 'Ninguno'},
        Valores_actuales={
            'Permisos': ', '.join(sorted(despues_set)) or 'Ninguno',
            'Agregados': ', '.join(sorted(despues_set - antes_set)) or '—',
            'Quitados': ', '.join(sorted(antes_set - despues_set)) or '—',
        },
    )

def accion_por_estado(antes, despues, campo_estado, valor_activo):
    """
    Si lo único que cambió es el estado -> BAJA o ACTIVACION.
    Si cambió cualquier otra cosa -> MODIFICACION.
    """
    campos = set(antes) | set(despues)
    cambiados = {c for c in campos if antes.get(c) != despues.get(c)}

    if cambiados == {campo_estado}:
        if despues.get(campo_estado) == valor_activo:
            return 'ACTIVACION'
        return 'BAJA'

    return 'MODIFICACION'