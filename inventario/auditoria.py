from datetime import date, datetime
from decimal import Decimal
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


def registrar_auditoria(usuario, entidad, objeto, accion, antes, despues):
    if accion == 'MODIFICACION' and antes == despues:
        return None

    return LogAuditoria.objects.create(
        ID_Usuario=usuario,
        Perfil_usuario=(
            usuario.ID_Perfil.Nombre_perfil
            if usuario and usuario.ID_Perfil
            else "Sin perfil"
        ),
        Entidad=entidad,
        ID_Registro=objeto.pk,
        Accion=accion,
        Valores_anteriores=antes,
        Valores_actuales=despues,
    )