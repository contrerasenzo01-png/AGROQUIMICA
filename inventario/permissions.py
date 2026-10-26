
from .models import Permisos


PERFILES_ADMIN = ('Administrador',)


MODULOS = {
    'usuarios': (
        None,
        'Gestionar usuarios',
    ),
    'perfiles': (
        None,
        'Gestionar perfiles',
    ),
    'permisos': (
        None,
        'Gestionar permisos',
    ),
    'proveedores': (
        'Consultar proveedores',
        'Gestionar proveedores',
    ),
    'productos': (
        'Consultar productos',
        'Gestionar productos',
    ),
    'remitos': (
        'Consultar remitos',
        'Gestionar remitos',
    ),
    'lotes': (
        'Consultar lotes',
        None,
    ),
    'movimientos': (
        'Consultar movimientos de stock',
        None,
    ),
    'tipos': (
        'Consultar tipos de productos',
        'Gestionar tipos de productos',
    ),
    'subtipos': (
        'Consultar subtipos',
        'Gestionar subtipos',
    ),
    'alertas': (
        'Consultar historial de alertas',
        None,
    ),
    'comprobantes': (
        None,
        'Emitir comprobantes',
    ),
}


def permisos_asignados(usuario):
    if not usuario or not usuario.ID_Perfil:
        return set()

    return {
        nombre.strip().lower()
        for nombre in usuario.ID_Perfil.permisos.values_list(
            'Nombre_permiso',
            flat=True,
        )
        if nombre
    }


def puede(usuario, modulo, gestionar=False, asignados=None):
    if not usuario or not usuario.ID_Perfil:
        return False

    if modulo not in MODULOS:
        return False

    if usuario.ID_Perfil.Nombre_perfil in PERFILES_ADMIN:
        return True

    if asignados is None:
        asignados = permisos_asignados(usuario)

    consultar, gestion = MODULOS[modulo]

    # Gestionar también permite consultar.
    if gestion and gestion.lower() in asignados:
        return True

    # Para gestionar, debe tener el permiso correspondiente.
    if gestionar:
        return False

    # Si el módulo no tiene permiso de consulta, no permite consultar.
    if not consultar:
        return False

    return consultar.lower() in asignados


def usuario_con_acceso(request, modulo, gestionar=False):
    from .views import usuario_autenticado

    usuario = usuario_autenticado(request)

    if not usuario:
        return None

    if not puede(usuario, modulo, gestionar=gestionar):
        return None

    return usuario