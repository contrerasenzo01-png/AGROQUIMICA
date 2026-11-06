from datetime import date, datetime
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.db.models.fields.files import FieldFile

from .models import LogAuditoria

CAMPOS_EXCLUIDOS = {'Contrasena','Fecha_ultima_modificacion'}   # nunca guardar el hash


def _serializar(valor):
    # Fotos (ImageField): se guarda el nombre del archivo, no el objeto.
    if isinstance(valor, FieldFile):
        return valor.name or 'Sin foto'
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


def _nombre_usuario(u):
    return f'{u.Apellido_usuario}, {u.Nombre_usuario}'


def _nombre_producto_id(id_producto):
    from .models import Productos
    producto = Productos.objects.filter(pk=id_producto).first()
    return producto.Nombre_producto if producto else None


def _nombre_por_seccion(seccion, pk):
    """Busca el registro original cuando el log no guarda su nombre."""
    from .models import (
        Alertas, Lotes, MovimientosStock, Perfiles, Productos, Proveedores,
        Remitos, Subtipos, TiposProductos, Usuarios,
    )

    buscadores = {
        'USUARIOS': (Usuarios, _nombre_usuario),
        'PERFILES': (Perfiles, lambda o: o.Nombre_perfil),
        'PRODUCTOS': (Productos, lambda o: o.Nombre_producto),
        'PROVEEDORES': (Proveedores, lambda o: o.nombre_proveedor),
        'TIPOS DE PRODUCTOS': (TiposProductos, lambda o: o.Nombre_tipo_producto),
        'SUBTIPOS': (Subtipos, lambda o: o.Nombre_subtipo),
        'REMITOS': (Remitos, lambda o: f'Remito {o.Numero_remito}'),
        'LOTES': (
            Lotes,
            lambda o: f'{o.ID_Producto.Nombre_producto} · Lote {o.Numero_lote}'
        ),
        'MOVIMIENTOS DE STOCK': (
            MovimientosStock,
            lambda o: f'{o.ID_Lote.ID_Producto.Nombre_producto} · '
                      f'Lote {o.ID_Lote.Numero_lote}'
        ),
        'HISTORIAL DE ALERTAS': (
            Alertas, lambda o: o.ID_Stock.ID_Producto.Nombre_producto
        ),
    }

    buscador = buscadores.get(str(seccion or '').strip().upper())
    if not buscador or pk is None:
        return None

    modelo, nombre = buscador
    try:
        objeto = modelo.objects.filter(pk=pk).first()
        return nombre(objeto) if objeto else None
    except Exception:
        return None


def nombre_registro(log):
    """
    Nombre del registro afectado por un log (producto, proveedor, usuario...).
    Primero lo busca en los datos guardados en el log (así funciona aunque el
    registro ya no exista); si no está, lo busca en la base.
    """
    anteriores = log.Valores_anteriores or {}
    actuales = log.Valores_actuales or {}

    def valor(clave):
        for datos in (actuales, anteriores):
            v = datos.get(clave)
            if v not in (None, ''):
                return v
        return None

    apellido, nombre = valor('Apellido_usuario'), valor('Nombre_usuario')
    if apellido or nombre:
        return ', '.join(str(x) for x in (apellido, nombre) if x)

    for clave in (
        'Nombre_producto', 'nombre_proveedor', 'Nombre_tipo_producto',
        'Nombre_subtipo', 'Nombre_perfil', 'Nombre_permiso',
    ):
        if valor(clave):
            return str(valor(clave))

    if valor('Numero_remito'):
        return f'Remito {valor("Numero_remito")}'

    lote = valor('Numero_lote') or valor('Lote')
    if valor('ID_Producto'):
        producto = _nombre_producto_id(valor('ID_Producto'))
        if producto:
            return f'{producto} · Lote {lote}' if lote else producto

    if valor('Nombre'):
        return str(valor('Nombre'))
    if valor('Usuario'):
        return str(valor('Usuario'))

    encontrado = _nombre_por_seccion(log.Seccion, log.ID_Registro)
    if encontrado:
        return encontrado

    return f'Lote {lote}' if lote else None


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


def registrar_bloqueo_inactividad(request, usuario, pantalla=''):
    """Registra que al usuario le apareció el aviso de bloqueo por inactividad.

    Se registra una sola vez por bloqueo (aunque tenga varias pestañas
    abiertas); la marca se borra al desbloquear la sesión.
    """
    if request.session.get('bloqueo_registrado'):
        return None

    request.session['bloqueo_registrado'] = True

    minutos = settings.INACTIVIDAD_SEGUNDOS // 60

    return LogAuditoria.objects.create(
        ID_Usuario=usuario,
        Seccion='Usuarios',
        ID_Registro=usuario.pk,
        Accion='BLOQUEO_INACTIVIDAD',
        Valores_anteriores={},
        Valores_actuales={
            'Usuario': usuario.Usuario,
            'Nombre': f'{usuario.Apellido_usuario}, {usuario.Nombre_usuario}',
            'Motivo': f'Más de {minutos} minutos sin actividad',
            'Pantalla': pantalla or '—',
        },
    )
