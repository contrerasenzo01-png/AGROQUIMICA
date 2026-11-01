"""
Catálogo de permisos del sistema.

Fuente de verdad: lo que está acá es lo que existe. El comando
`python manage.py sync_permisos` lo copia a la tabla PERMISOS.
Desde la pantalla de Perfiles solo se ASIGNAN estos permisos.

  - "Consultar X"  -> ver el listado / detalle del módulo.
  - "Gestionar X"  -> crear, editar, cambiar estado y eliminar. Incluye consultar.
  - Acciones sensibles (anular remitos, atender alertas) tienen permiso propio.
El perfil "Administrador" siempre tiene todo.
"""

PERFILES_ADMIN = ('Administrador',)
from django.urls import NoReverseMatch, reverse

# El orden de este diccionario es el orden en que se muestran.
CATALOGO = {
    'usuarios': {
        'titulo': 'Usuarios',
        'consultar': ('Consultar usuarios',
                      'Ver el listado de usuarios del sistema.'),
        'gestionar': ('Gestionar usuarios',
                      'Crear, editar, dar de baja, activar y eliminar usuarios, y restablecer contraseñas.'),
    },
    'productos': {
        'titulo': 'Productos',
        'consultar': ('Consultar productos',
                      'Ver productos, stock y lotes de cada producto.'),
        'gestionar': ('Gestionar productos',
                      'Crear, editar y eliminar productos y su stock mínimo.'),
    },
    'tipos': {
        'titulo': 'Tipos de productos',
        'consultar': ('Consultar tipos de productos',
                      'Ver los tipos de productos.'),
        'gestionar': ('Gestionar tipos de productos',
                      'Crear, editar y eliminar tipos de productos.'),
    },
    'subtipos': {
        'titulo': 'Subtipos',
        'consultar': ('Consultar subtipos', 'Ver los subtipos.'),
        'gestionar': ('Gestionar subtipos',
                      'Crear, editar y eliminar subtipos.'),
    },
    'proveedores': {
        'titulo': 'Proveedores',
        'consultar': ('Consultar proveedores', 'Ver los proveedores.'),
        'gestionar': ('Gestionar proveedores',
                      'Crear, editar, dar de baja, activar y eliminar proveedores.'),
    },
    'remitos': {
        'titulo': 'Remitos',
        'consultar': ('Consultar remitos',
                      'Ver remitos y los lotes que ingresaron con cada uno.'),
        'gestionar': ('Gestionar remitos',
                      'Registrar remitos con sus lotes y corregir remitos y lotes.'),
    },
    'lotes': {
        'titulo': 'Lotes',
        'consultar': ('Consultar lotes', 'Ver el listado de lotes y sus vencimientos.'),
    },
    'movimientos': {
        'titulo': 'Movimientos de stock',
        'consultar': ('Consultar movimientos de stock',
                      'Ver entradas, egresos y anulaciones de stock.'),
    },
    'comprobantes': {
        'titulo': 'Movimientos de stock',
        'gestionar': ('Emitir comprobantes',
                      'Generar el comprobante PDF de un movimiento de stock.'),
    },
    'egresos': {
        'titulo': 'Movimientos de stock',
        'gestionar': ('Registrar egresos de stock',
                      'Registrar salidas de stock por venta.'),
    },
    'alertas': {
        'titulo': 'Alertas',
        'consultar': ('Consultar historial de alertas',
                      'Ver el historial de alertas de vencimiento y stock bajo.'),
    },
    'reportes': {
        'titulo': 'Reportes',
        'consultar': ('Consultar reportes',
                      'Ver los gráficos y reportes del sistema.'),
    },
    'perfiles': {
        'titulo': 'Seguridad',
        'consultar': ('Consultar perfiles',
                      'Ver los perfiles de acceso y sus permisos.'),
        'gestionar': ('Gestionar perfiles',
                      'Crear, editar, activar y eliminar perfiles y asignarles permisos.'),
    },
    'permisos': {
        'titulo': 'Seguridad',
        'consultar': ('Consultar permisos',
                      'Ver el catálogo de permisos del sistema.'),
    },
    'auditoria': {
        'titulo': 'Seguridad',
        'consultar': ('Consultar auditoría',
                      'Ver el registro de auditoría y su detalle.'),
    },
}

# Acciones sensibles con permiso propio: clave -> (nombre, descripción, grupo)
ACCIONES = {
    'anular_remitos': ('Anular remitos',
                       'Anular un remito y revertir su ingreso de stock.', 'Remitos'),
    'atender_alertas': ('Atender alertas',
                        'Marcar alertas como atendidas.', 'Alertas'),
}

# Derivado del catálogo: modulo -> (nombre_consultar, nombre_gestionar)
MODULOS = {
    modulo: (
        (datos.get('consultar') or (None,))[0],
        (datos.get('gestionar') or (None,))[0],
    )
    for modulo, datos in CATALOGO.items()
}


def catalogo_plano():
    """Lista de (nombre, descripcion, grupo) sin repetidos."""
    filas, vistos = [], set()
    for datos in CATALOGO.values():
        for tipo in ('consultar', 'gestionar'):
            if datos.get(tipo) and datos[tipo][0] not in vistos:
                vistos.add(datos[tipo][0])
                filas.append((datos[tipo][0], datos[tipo][1], datos['titulo']))
    for nombre, desc, grupo in ACCIONES.values():
        filas.append((nombre, desc, grupo))
    return filas


# ------------------------------------------------------------
# CONSULTA DE PERMISOS
# ------------------------------------------------------------

def _es_admin(usuario):
    return usuario.ID_Perfil.Nombre_perfil in PERFILES_ADMIN


def permisos_asignados(usuario):
    """Nombres (en minúsculas) de los permisos del perfil. Se cachea en el objeto."""
    if not usuario or not usuario.ID_Perfil:
        return set()

    cache = getattr(usuario, '_permisos_cache', None)

    if cache is None:
        cache = {
            nombre.strip().lower()
            for nombre in usuario.ID_Perfil.permisos.values_list(
                'Nombre_permiso', flat=True
            )
            if nombre
        }
        usuario._permisos_cache = cache

    return cache


def puede(usuario, modulo, gestionar=False, asignados=None):
    if not usuario or not usuario.ID_Perfil:
        return False

    if modulo not in MODULOS:
        return False

    if _es_admin(usuario):
        return True

    if asignados is None:
        asignados = permisos_asignados(usuario)

    consultar, gestion = MODULOS[modulo]

    # Gestionar también permite consultar.
    if gestion and gestion.lower() in asignados:
        return True

    if gestionar:
        return False

    if not consultar:
        return False

    return consultar.lower() in asignados


def puede_accion(usuario, accion):
    """Permisos de acciones sensibles (ver ACCIONES)."""
    if not usuario or not usuario.ID_Perfil or accion not in ACCIONES:
        return False

    if _es_admin(usuario):
        return True

    return ACCIONES[accion][0].lower() in permisos_asignados(usuario)


def usuario_con_acceso(request, modulo, gestionar=False):
    from .views import usuario_autenticado

    usuario = usuario_autenticado(request)

    if not usuario:
        return None

    if not puede(usuario, modulo, gestionar=gestionar):
        request.permiso_denegado = True
        return None

    return usuario


def usuario_con_accion(request, accion):
    from .views import usuario_autenticado

    usuario = usuario_autenticado(request)

    if not usuario:
        return None

    if not puede_accion(usuario, accion):
        request.permiso_denegado = True
        return None

    return usuario


# ------------------------------------------------------------
# MENÚ LATERAL (se arma según los permisos)
# ------------------------------------------------------------

# (modulo, nombre_de_url, icono, texto)
MENU = [
    ('ADMINISTRACIÓN', [
        ('usuarios', 'gestion_usuarios', 'i-users', 'Usuarios del sistema'),
    ]),
    ('INVENTARIO', [
        ('productos', 'gestion_productos', 'i-package', 'Productos y stock'),
        ('tipos', 'gestion_tipos_productos', 'i-layers', 'Tipos de productos'),
        ('subtipos', 'gestion_subtipos', 'i-tags', 'Subtipos'),
        ('proveedores', 'gestion_proveedores', 'i-truck', 'Proveedores'),
        ('remitos', 'gestion_remitos', 'i-inbox', 'Remitos'),
        ('lotes', 'registrar_ingreso_lote', 'i-package', 'Lotes'),
        ('movimientos', 'gestion_movimientos_stock', 'i-swap', 'Movimientos de stock'),
        ('alertas', 'historial_alertas', 'i-bell', 'Historial de alertas'),
    ]),
    ('ANÁLISIS', [
        ('reportes', 'gestion_reportes', 'i-chart', 'Reportes'),
    ]),
    ('SEGURIDAD', [
        ('perfiles', 'gestion_perfiles', 'i-shield', 'Perfiles de acceso'),
        ('permisos', 'gestion_permisos', 'i-key', 'Permisos del sistema'),
        ('auditoria', 'gestion_auditoria', 'i-shield', 'Auditoría'),
    ]),
]


def menu_para(usuario):
    if not usuario or not usuario.ID_Perfil:
        return []

    asignados = None if _es_admin(usuario) else permisos_asignados(usuario)
    secciones = []

    for titulo, items in MENU:
        visibles = [
            {'modulo': m, 'url': url, 'icono': icono, 'texto': texto}
            for m, url, icono, texto in items
            if puede(usuario, m, asignados=asignados)
        ]
        if visibles:
            secciones.append({'titulo': titulo, 'items': visibles})

    if not _es_admin(usuario):
        secciones.append({
            'titulo': 'MI CUENTA',
            'items': [{
                'modulo': 'mis_permisos', 'url': 'mis_permisos',
                'icono': 'i-key', 'texto': 'Mis permisos',
            }],
        })

    return secciones

# ------------------------------------------------------------
# RUTAS DE ACCIÓN QUE EL USUARIO NO PUEDE USAR
# (el navegador avisa antes de enviar el formulario)
# ------------------------------------------------------------

RUTAS_GESTION = {
    'usuarios': ['crear_usuario', 'editar_usuario', 'dar_baja_usuario',
                 'activar_usuario', 'restablecer_contrasena', 'eliminar_usuario'],
    'productos': ['crear_producto', 'editar_producto', 'eliminar_producto'],
    'tipos': ['crear_tipo_producto', 'editar_tipo_producto', 'eliminar_tipo_producto'],
    'subtipos': ['crear_subtipo', 'editar_subtipo', 'eliminar_subtipo'],
    'proveedores': ['crear_proveedor', 'editar_proveedor',
                    'cambiar_estado_proveedor', 'eliminar_proveedor'],
    'perfiles': ['crear_perfil', 'editar_perfil',
                 'cambiar_estado_perfil', 'eliminar_perfil'],
    'egresos': ['registrar_egreso'],
    'comprobantes': ['comprobante_movimiento_pdf'],
}

RUTAS_ACCION = {
    'atender_alertas': ['atender_alerta'],
}

_MARCA = 987654321


def _patron(nombre):
    """Ruta de una vista; el ID se reemplaza por * (ej: /productos/eliminar/*/)."""
    try:
        return reverse(nombre)
    except NoReverseMatch:
        return reverse(nombre, args=[_MARCA]).replace(str(_MARCA), '*')


def rutas_denegadas(usuario):
    if not usuario or not usuario.ID_Perfil or _es_admin(usuario):
        return []

    asignados = permisos_asignados(usuario)
    patrones = []

    for modulo, nombres in RUTAS_GESTION.items():
        if not puede(usuario, modulo, gestionar=True, asignados=asignados):
            patrones += [_patron(n) for n in nombres]

    for accion, nombres in RUTAS_ACCION.items():
        if not puede_accion(usuario, accion):
            patrones += [_patron(n) for n in nombres]

    return patrones