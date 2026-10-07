from datetime import timedelta
from decimal import Decimal, InvalidOperation
import unicodedata

from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .forms import ProveedorForm

from .models import (
    TiposProductos,
    Subtipos,
    Proveedores,
    TiposMovimientos,
    Perfiles,
    Permisos,
    PerfilesXPermisos,
    Usuarios,
    Productos,
    Lotes,
    Stock,
    Alertas,
    MovimientosStock
)


# ============================================================
# CONTROL DE ACCESO
# ============================================================

# Perfiles que pueden entrar a las pantallas de administración.
# Si renombrás el perfil en la base, agregá el nombre nuevo acá.
PERFILES_ADMIN = ('Administrador', 'Jefe')


def usuario_autenticado(request):
    """Devuelve el usuario logueado si está activo y con perfil activo."""

    usuario_id = request.session.get('usuario_id')

    if not usuario_id:
        return None

    try:
        usuario = Usuarios.objects.select_related(
            'ID_Perfil'
        ).get(
            ID_Usuario=usuario_id
        )
    except Usuarios.DoesNotExist:
        return None

    if not usuario.Estado_usuario:
        return None

    if not usuario.ID_Perfil:
        return None

    if not usuario.ID_Perfil.Estado_perfil:
        return None

    return usuario


def usuario_es_administrador(request):
    """Igual que usuario_autenticado, pero solo para perfiles de administración."""

    usuario = usuario_autenticado(request)

    if not usuario:
        return None

    if usuario.ID_Perfil.Nombre_perfil not in PERFILES_ADMIN:
        return None

    return usuario


# ============================================================
# LOGIN
# ============================================================

def login_view(request):

    error_message = None

    if request.method == 'POST':

        usuario_input = request.POST.get('usuario', '').strip()
        password_input = request.POST.get('password', '')

        try:

            usuario = Usuarios.objects.select_related(
                'ID_Perfil'
            ).get(
                Usuario=usuario_input
            )

            if not usuario.Estado_usuario:

                error_message = 'El usuario se encuentra inactivo.'

            elif not usuario.ID_Perfil:

                error_message = 'El usuario no tiene un perfil asignado.'

            elif not usuario.ID_Perfil.Estado_perfil:

                error_message = 'El perfil del usuario se encuentra inactivo.'

            elif check_password(password_input, usuario.Contrasena):

                request.session['usuario_id'] = usuario.ID_Usuario
                request.session['usuario_nombre'] = usuario.Usuario
                request.session['perfil_id'] = usuario.ID_Perfil.ID_Perfil
                request.session['perfil_nombre'] = usuario.ID_Perfil.Nombre_perfil

                if usuario.Cambiar_contrasena:
                    return redirect('cambiar_contrasena')

                return redirect('panel_principal')

            else:

                error_message = 'Usuario o contraseña incorrectos.'

        except Usuarios.DoesNotExist:

            error_message = 'Usuario o contraseña incorrectos.'

    return render(
        request,
        'inventario/login.html',
        {
            'error': error_message
        }
    )


def cerrar_sesion(request):

    request.session.flush()

    return redirect('login')


# ============================================================
# PANEL PRINCIPAL
# ============================================================

def panel_principal(request):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    generar_alertas_vencimiento()

    return render(
        request,
        'inventario/panel_principal.html',
        {
            'usuario': usuario
        }
    )


# ============================================================
# PROVEEDORES
# ============================================================

def _proveedor_duplicado(form, excluir_pk=None):
    """Busca otro proveedor que coincida en nombre, teléfono, email o dirección."""

    nombre = form.cleaned_data['nombre_proveedor'].strip()
    telefono = (form.cleaned_data.get('telefono_proveedor') or '').strip()
    email = (form.cleaned_data.get('email_proveedor') or '').strip()
    direccion = (form.cleaned_data.get('direccion_proveedor') or '').strip()

    filtros = Q(nombre_proveedor__iexact=nombre)

    if telefono:
        filtros |= Q(telefono_proveedor=telefono)

    if email:
        filtros |= Q(email_proveedor__iexact=email)

    if direccion:
        filtros |= Q(direccion_proveedor__iexact=direccion)

    proveedores = Proveedores.objects.filter(filtros)

    if excluir_pk is not None:
        proveedores = proveedores.exclude(ID_Proveedor=excluir_pk)

    return proveedores.first()


def gestion_proveedores(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()

    proveedores = Proveedores.objects.all()

    if busqueda:

        proveedores = proveedores.filter(
            Q(nombre_proveedor__icontains=busqueda) |
            Q(email_proveedor__icontains=busqueda) |
            Q(direccion_proveedor__icontains=busqueda) |
            Q(telefono_proveedor__icontains=busqueda)
        )

    total_proveedores = Proveedores.objects.count()

    proveedores_activos = Proveedores.objects.filter(
        estado_proveedor=True
    ).count()

    form = ProveedorForm()

    error_duplicado_id = request.session.pop('error_duplicado_id', None)
    proveedor_conflicto = request.session.pop('proveedor_conflicto', None)

    return render(
        request,
        'inventario/proveedores.html',
        {
            'usuario': usuario,
            'proveedores': proveedores,
            'total_proveedores': total_proveedores,
            'proveedores_activos': proveedores_activos,
            'form': form,
            'error_duplicado_id': error_duplicado_id,
            'proveedor_conflicto': proveedor_conflicto,
        }
    )


def crear_proveedor(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    if request.method == 'POST':

        form = ProveedorForm(request.POST)

        if form.is_valid():

            existente = _proveedor_duplicado(form)

            if existente:

                request.session['error_duplicado_id'] = existente.ID_Proveedor
                request.session['proveedor_conflicto'] = (
                    'Ya existe un proveedor con alguno '
                    'de los datos ingresados.'
                )

                return redirect('gestion_proveedores')

            form.save()

            return redirect('gestion_proveedores')

    else:

        form = ProveedorForm()

    return render(
        request,
        'inventario/crear_proveedor.html',
        {
            'usuario': usuario,
            'form': form
        }
    )


def editar_proveedor(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    proveedor = get_object_or_404(Proveedores, ID_Proveedor=pk)

    if request.method == 'POST':

        form = ProveedorForm(request.POST, instance=proveedor)

        if form.is_valid():

            existente = _proveedor_duplicado(form, excluir_pk=pk)

            if existente:

                request.session['error_duplicado_id'] = existente.ID_Proveedor
                request.session['proveedor_conflicto'] = (
                    'Ya existe otro proveedor con alguno '
                    'de los datos ingresados.'
                )

                return redirect('gestion_proveedores')

            form.save()

            return redirect('gestion_proveedores')

    else:

        form = ProveedorForm(instance=proveedor)

    return render(
        request,
        'inventario/editar_proveedor.html',
        {
            'usuario': usuario,
            'form': form,
            'proveedor': proveedor
        }
    )


def cambiar_estado_proveedor(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    proveedor = get_object_or_404(Proveedores, ID_Proveedor=pk)

    if request.method == 'POST':

        proveedor.estado_proveedor = not proveedor.estado_proveedor
        proveedor.save()

    return redirect('gestion_proveedores')


# ============================================================
# TIPOS DE PRODUCTOS
# ============================================================

def gestion_tipos_productos(request):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    busqueda = request.GET.get('q', '').strip()

    tipos = TiposProductos.objects.all()

    if busqueda:
        tipos = tipos.filter(Nombre_tipo_producto__icontains=busqueda)

    return render(
        request,
        'inventario/tipos_productos.html',
        {
            'tipos_productos': tipos,
            'busqueda': busqueda,
            'usuario': usuario,
            'total_tipos': TiposProductos.objects.count(),
            'total_subtipos': Subtipos.objects.count()
        }
    )


def crear_tipo_producto(request):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    if request.method == 'POST':

        nombre = request.POST.get('Nombre_tipo_producto', '').strip()

        if not nombre:

            messages.error(request, 'Debe ingresar el nombre del tipo de producto.')

            return redirect('gestion_tipos_productos')

        existe = TiposProductos.objects.filter(
            Nombre_tipo_producto__iexact=nombre
        ).exists()

        if existe:

            messages.error(request, 'Ya existe un tipo de producto con ese nombre.')

            return redirect('gestion_tipos_productos')

        TiposProductos.objects.create(Nombre_tipo_producto=nombre)

        messages.success(request, 'Tipo de producto registrado correctamente.')

    return redirect('gestion_tipos_productos')


def editar_tipo_producto(request, pk):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    tipo = get_object_or_404(TiposProductos, ID_Tipo_producto=pk)

    if request.method == 'POST':

        nombre = request.POST.get('Nombre_tipo_producto', '').strip()

        if not nombre:

            messages.error(request, 'Debe ingresar el nombre del tipo de producto.')

            return redirect('gestion_tipos_productos')

        existe = TiposProductos.objects.filter(
            Nombre_tipo_producto__iexact=nombre
        ).exclude(
            ID_Tipo_producto=pk
        ).exists()

        if existe:

            messages.error(request, 'Ya existe otro tipo de producto con ese nombre.')

            return redirect('gestion_tipos_productos')

        tipo.Nombre_tipo_producto = nombre
        tipo.save()

        messages.success(request, 'Tipo de producto actualizado correctamente.')

    return redirect('gestion_tipos_productos')


def dar_baja_tipo_producto(request, pk):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    tipo = get_object_or_404(TiposProductos, ID_Tipo_producto=pk)

    if request.method == 'POST':

        estado = request.POST.get('estado')

        if estado == 'activo':

            tipo.Estado_tipo_producto = True

            messages.success(request, 'Tipo de producto activado correctamente.')

        elif estado == 'inactivo':

            tipo.Estado_tipo_producto = False

            messages.success(request, 'Tipo de producto dado de baja correctamente.')

        tipo.save()

    return redirect('gestion_tipos_productos')


# ============================================================
# SUBTIPOS
# ============================================================

def _subtipo_tiene_descripcion():
    """True si el modelo Subtipos tiene el campo Descripcion_subtipo (como en el DER)."""

    return any(f.name == 'Descripcion_subtipo' for f in Subtipos._meta.get_fields())


def gestion_subtipos(request):

    # CORREGIDO: antes usaba usuario_autenticado, pero el menú de Subtipos
    # es solo de administración y crear/editar ya exigían ser administrador.
    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()

    subtipos = Subtipos.objects.select_related('ID_Tipo_producto').all()

    if busqueda:
        subtipos = subtipos.filter(Nombre_subtipo__icontains=busqueda)

    tipos_productos = TiposProductos.objects.filter(
        Estado_tipo_producto=True
    ).order_by(
        'Nombre_tipo_producto'
    )

    return render(
        request,
        'inventario/subtipos.html',
        {
            'subtipos': subtipos,
            'tipos_productos': tipos_productos,
            'busqueda': busqueda,
            'usuario': usuario,
            'total_tipos': TiposProductos.objects.count(),
            'total_subtipos': Subtipos.objects.count()
        }
    )


def crear_subtipo(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    if request.method == 'POST':

        nombre = request.POST.get('Nombre_subtipo', '').strip()
        tipo_id = request.POST.get('ID_Tipo_producto')

        if not nombre:

            messages.error(request, 'Debe ingresar el nombre del subtipo.')

            return redirect('gestion_subtipos')

        if not tipo_id:

            messages.error(request, 'Debe seleccionar un tipo de producto.')

            return redirect('gestion_subtipos')

        tipo = get_object_or_404(
            TiposProductos,
            ID_Tipo_producto=tipo_id,
            Estado_tipo_producto=True
        )

        existe = Subtipos.objects.filter(
            ID_Tipo_producto=tipo,
            Nombre_subtipo__iexact=nombre
        ).exists()

        if existe:

            messages.error(
                request,
                'Ya existe un subtipo con ese nombre para el tipo seleccionado.'
            )

            return redirect('gestion_subtipos')

        datos_subtipo = {
            'ID_Tipo_producto': tipo,
            'Nombre_subtipo': nombre,
            'Estado_subtipo': True
        }

        if _subtipo_tiene_descripcion():
            datos_subtipo['Descripcion_subtipo'] = (
                request.POST.get('Descripcion_subtipo', '').strip() or None
            )

        Subtipos.objects.create(**datos_subtipo)

        messages.success(request, 'Subtipo creado correctamente.')

    return redirect('gestion_subtipos')


def editar_subtipo(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    subtipo = get_object_or_404(Subtipos, ID_Subtipo=pk)

    if request.method == 'POST':

        nombre = request.POST.get('Nombre_subtipo', '').strip()
        tipo_id = request.POST.get('ID_Tipo_producto')

        if not nombre:

            messages.error(request, 'Debe ingresar el nombre del subtipo.')

            return redirect('gestion_subtipos')

        if not tipo_id:

            messages.error(request, 'Debe seleccionar un tipo de producto.')

            return redirect('gestion_subtipos')

        tipo = get_object_or_404(
            TiposProductos,
            ID_Tipo_producto=tipo_id,
            Estado_tipo_producto=True
        )

        existe = Subtipos.objects.filter(
            ID_Tipo_producto=tipo,
            Nombre_subtipo__iexact=nombre
        ).exclude(
            ID_Subtipo=pk
        ).exists()

        if existe:

            messages.error(
                request,
                'Ya existe un subtipo con ese nombre para el tipo seleccionado.'
            )

            return redirect('gestion_subtipos')

        subtipo.ID_Tipo_producto = tipo
        subtipo.Nombre_subtipo = nombre

        if _subtipo_tiene_descripcion():
            subtipo.Descripcion_subtipo = (
                request.POST.get('Descripcion_subtipo', '').strip() or None
            )

        subtipo.save()

        messages.success(request, 'Subtipo modificado correctamente.')

    return redirect('gestion_subtipos')


def cambiar_estado_subtipo(request, pk):

    # CORREGIDO: antes cualquier usuario logueado (incluido Vendedor)
    # podía activar o dar de baja subtipos.
    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    subtipo = get_object_or_404(Subtipos, ID_Subtipo=pk)

    if request.method == 'POST':

        subtipo.Estado_subtipo = not subtipo.Estado_subtipo
        subtipo.save()

        if subtipo.Estado_subtipo:
            messages.success(request, 'Subtipo activado correctamente.')
        else:
            messages.success(request, 'Subtipo dado de baja correctamente.')

    return redirect('gestion_subtipos')


# ============================================================
# GESTIONAR USUARIOS
# ============================================================

def gestion_usuarios(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()

    usuarios = Usuarios.objects.select_related('ID_Perfil').all()

    if busqueda:

        filtros = (
            Q(Nombre_usuario__icontains=busqueda) |
            Q(Apellido_usuario__icontains=busqueda) |
            Q(Usuario__icontains=busqueda) |
            Q(Email_usuario__icontains=busqueda)
        )

        if busqueda.isdigit():
            filtros |= Q(DNI=int(busqueda))

        usuarios = usuarios.filter(filtros)

    perfiles = Perfiles.objects.all()

    return render(
        request,
        'inventario/usuarios.html',
        {
            'usuarios': usuarios,
            'perfiles': perfiles,
            'busqueda': busqueda,
            'usuario_actual': usuario,
            # CORREGIDO: el menú lateral (_sidebar.html) lee 'usuario'
            'usuario': usuario
        }
    )


def crear_usuario(request):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    if request.method == 'POST':

        perfil_id = request.POST.get('ID_Perfil')

        if not perfil_id:

            messages.error(request, 'Debe seleccionar un perfil.')

            return redirect('gestion_usuarios')

        perfil = get_object_or_404(Perfiles, ID_Perfil=perfil_id)

        dni = request.POST.get('DNI', '').strip()
        apellido = request.POST.get('Apellido_usuario', '').strip()
        nombre = request.POST.get('Nombre_usuario', '').strip()
        email = request.POST.get('Email_usuario', '').strip()
        contrasena = request.POST.get('Contrasena', '').strip()

        if not dni or not dni.isdigit():

            messages.error(request, 'Debe ingresar un DNI válido.')

            return redirect('gestion_usuarios')

        if not nombre:

            messages.error(request, 'Debe ingresar el nombre del usuario.')

            return redirect('gestion_usuarios')

        if not apellido:

            messages.error(request, 'Debe ingresar el apellido del usuario.')

            return redirect('gestion_usuarios')

        if not email:

            messages.error(request, 'Debe ingresar el correo electrónico.')

            return redirect('gestion_usuarios')

        if len(contrasena) < 8:

            messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')

            return redirect('gestion_usuarios')

        if Usuarios.objects.filter(DNI=int(dni)).exists():

            messages.error(request, 'Ya existe un usuario con ese DNI.')

            return redirect('gestion_usuarios')

        if Usuarios.objects.filter(Email_usuario__iexact=email).exists():

            messages.error(request, 'Ya existe un usuario con ese correo electrónico.')

            return redirect('gestion_usuarios')

        apellido_sin_tildes = ''.join(
            caracter
            for caracter in unicodedata.normalize('NFD', apellido)
            if unicodedata.category(caracter) != 'Mn'
        )

        nombre_sin_tildes = ''.join(
            caracter
            for caracter in unicodedata.normalize('NFD', nombre)
            if unicodedata.category(caracter) != 'Mn'
        )

        usuario_generado = (
            apellido_sin_tildes + nombre_sin_tildes[0]
        ).lower()

        if Usuarios.objects.filter(Usuario=usuario_generado).exists():

            messages.error(request, f'El usuario {usuario_generado} ya existe.')

            return redirect('gestion_usuarios')

        nuevo = Usuarios.objects.create(
            ID_Perfil=perfil,
            DNI=int(dni),
            Apellido_usuario=apellido,
            Nombre_usuario=nombre,
            Usuario=usuario_generado,
            Contrasena=make_password(contrasena),
            Email_usuario=email,
            Estado_usuario=True,
            Cambiar_contrasena=True
        )

        messages.success(
            request,
            f'El usuario {nuevo.Usuario} '
            f'ha sido registrado correctamente. '
            f'Deberá cambiar su contraseña '
            f'en el próximo inicio de sesión.'
        )

    return redirect('gestion_usuarios')


def editar_usuario(request, pk):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(Usuarios, ID_Usuario=pk)

    if request.method == 'POST':

        nuevo_email = request.POST.get('Email_usuario', '').strip()

        if not nuevo_email:

            messages.error(request, 'El correo electrónico es obligatorio.')

            return render(
                request,
                'inventario/editar_usuario.html',
                {'usuario': usuario}
            )

        email_existente = Usuarios.objects.filter(
            Email_usuario__iexact=nuevo_email
        ).exclude(
            ID_Usuario=pk
        ).exists()

        if email_existente:

            messages.error(request, 'Ya existe otro usuario con ese correo electrónico.')

            return render(
                request,
                'inventario/editar_usuario.html',
                {'usuario': usuario}
            )

        usuario.Email_usuario = nuevo_email
        usuario.save()

        messages.success(
            request,
            f'El usuario {usuario.Usuario} '
            f'ha sido modificado correctamente.'
        )

        return redirect('gestion_usuarios')

    return render(
        request,
        'inventario/editar_usuario.html',
        {'usuario': usuario}
    )


def dar_baja_usuario(request, pk):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(Usuarios, ID_Usuario=pk)

    if usuario.ID_Usuario == usuario_admin.ID_Usuario:

        messages.error(request, 'No puede darse de baja a sí mismo.')

        return redirect('gestion_usuarios')

    if request.method == 'POST':

        usuario.Estado_usuario = False
        usuario.Fecha_Baja = timezone.now().date()
        usuario.save()

        messages.success(request, 'Usuario dado de baja correctamente.')

    return redirect('gestion_usuarios')


def activar_usuario(request, id):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(Usuarios, ID_Usuario=id)

    if request.method == 'POST':

        usuario.Estado_usuario = True
        usuario.Fecha_Baja = None
        usuario.save()

        messages.success(
            request,
            f'El usuario {usuario.Usuario} fue activado correctamente.'
        )

    return redirect('gestion_usuarios')


def restablecer_contrasena(request, pk):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(Usuarios, ID_Usuario=pk)

    if request.method == 'POST':

        nueva_contrasena = request.POST.get('nueva_contrasena', '')
        confirmar_contrasena = request.POST.get('confirmar_contrasena', '')

        if nueva_contrasena != confirmar_contrasena:

            messages.error(request, 'Las contraseñas no coinciden.')

            return render(
                request,
                'inventario/restablecer_contrasena.html',
                {'usuario': usuario}
            )

        if len(nueva_contrasena) < 8:

            messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')

            return render(
                request,
                'inventario/restablecer_contrasena.html',
                {'usuario': usuario}
            )

        usuario.Contrasena = make_password(nueva_contrasena)
        usuario.Cambiar_contrasena = True
        usuario.save()

        messages.success(
            request,
            f'La contraseña del usuario {usuario.Usuario} '
            'fue restablecida correctamente. '
            'Deberá cambiarla en el próximo inicio de sesión.'
        )

        return redirect('gestion_usuarios')

    return render(
        request,
        'inventario/restablecer_contrasena.html',
        {'usuario': usuario}
    )


def cambiar_contrasena(request):

    usuario_id = request.session.get('usuario_id')

    if not usuario_id:
        return redirect('login')

    usuario = get_object_or_404(Usuarios, ID_Usuario=usuario_id)

    if request.method == 'POST':

        nueva_contrasena = request.POST.get('nueva_contrasena', '')
        confirmar_contrasena = request.POST.get('confirmar_contrasena', '')

        if nueva_contrasena != confirmar_contrasena:

            messages.error(request, 'Las contraseñas no coinciden.')

            return render(request, 'inventario/cambiar_contrasena.html')

        if len(nueva_contrasena) < 8:

            messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')

            return render(request, 'inventario/cambiar_contrasena.html')

        usuario.Contrasena = make_password(nueva_contrasena)
        usuario.Cambiar_contrasena = False
        usuario.save()

        messages.success(request, 'Contraseña cambiada correctamente.')

        return redirect('panel_principal')

    return render(request, 'inventario/cambiar_contrasena.html')


# ============================================================
# GESTIÓN DE PERFILES
# ============================================================

def gestion_perfiles(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()

    perfiles = Perfiles.objects.prefetch_related('permisos').all()

    if busqueda:
        perfiles = perfiles.filter(Nombre_perfil__icontains=busqueda)

    permisos = Permisos.objects.all()

    return render(
        request,
        'inventario/perfiles.html',
        {
            'perfiles': perfiles,
            'permisos': permisos,
            'busqueda': busqueda,
            'usuario': usuario
        }
    )


def crear_perfil(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    if request.method == 'POST':

        nombre_perfil = request.POST.get('Nombre_perfil', '').strip()

        if not nombre_perfil:

            messages.error(request, 'Debe ingresar el nombre del perfil.')

            return redirect('gestion_perfiles')

        if Perfiles.objects.filter(Nombre_perfil__iexact=nombre_perfil).exists():

            messages.error(request, 'Ya existe un perfil con ese nombre.')

            return redirect('gestion_perfiles')

        permisos_ids = request.POST.getlist('permisos')

        # CORREGIDO: perfil y permisos se guardan juntos; si un permiso
        # no existe, no queda un perfil a medio crear.
        with transaction.atomic():

            perfil = Perfiles.objects.create(Nombre_perfil=nombre_perfil)

            for permiso_id in permisos_ids:

                permiso = get_object_or_404(Permisos, ID_Permiso=permiso_id)

                PerfilesXPermisos.objects.create(
                    ID_Perfil=perfil,
                    ID_Permiso=permiso
                )

        messages.success(request, 'Perfil creado correctamente.')

    return redirect('gestion_perfiles')


def editar_perfil(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    perfil = get_object_or_404(Perfiles, ID_Perfil=pk)

    if request.method == 'POST':

        nombre_perfil = request.POST.get('Nombre_perfil', '').strip()

        if not nombre_perfil:

            messages.error(request, 'Debe ingresar el nombre del perfil.')

            return redirect('gestion_perfiles')

        existe = Perfiles.objects.filter(
            Nombre_perfil__iexact=nombre_perfil
        ).exclude(
            ID_Perfil=pk
        ).exists()

        if existe:

            messages.error(request, 'Ya existe otro perfil con ese nombre.')

            return redirect('gestion_perfiles')

        permisos_ids = request.POST.getlist('permisos')

        # CORREGIDO: antes se borraban los permisos y, si algo fallaba
        # después, el perfil quedaba sin permisos. Ahora es todo o nada.
        with transaction.atomic():

            perfil.Nombre_perfil = nombre_perfil
            perfil.save()

            PerfilesXPermisos.objects.filter(ID_Perfil=perfil).delete()

            for permiso_id in permisos_ids:

                permiso = get_object_or_404(Permisos, ID_Permiso=permiso_id)

                PerfilesXPermisos.objects.create(
                    ID_Perfil=perfil,
                    ID_Permiso=permiso
                )

        messages.success(request, 'Perfil actualizado correctamente.')

    return redirect('gestion_perfiles')


def cambiar_estado_perfil(request, id):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    perfil = get_object_or_404(Perfiles, ID_Perfil=id)

    if request.method == 'POST':

        # CORREGIDO: evita que el administrador dé de baja su propio perfil
        # y se deje sin acceso al sistema.
        if perfil.ID_Perfil == usuario.ID_Perfil.ID_Perfil and perfil.Estado_perfil:

            messages.error(request, 'No puede dar de baja el perfil con el que inició sesión.')

            return redirect('gestion_perfiles')

        perfil.Estado_perfil = not perfil.Estado_perfil
        perfil.save(update_fields=['Estado_perfil'])

        if perfil.Estado_perfil:

            messages.success(
                request,
                f'El perfil "{perfil.Nombre_perfil}" fue activado correctamente.'
            )

        else:

            messages.success(
                request,
                f'El perfil "{perfil.Nombre_perfil}" fue dado de baja correctamente.'
            )

    return redirect('gestion_perfiles')


# ============================================================
# GESTIÓN DE PERMISOS
# ============================================================

def gestion_permisos(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()

    permisos = Permisos.objects.prefetch_related('perfiles').all()

    if busqueda:

        permisos = permisos.filter(
            Q(Nombre_permiso__icontains=busqueda) |
            Q(Descripcion_permiso__icontains=busqueda)
        )

    return render(
        request,
        'inventario/permisos.html',
        {
            'permisos': permisos,
            'busqueda': busqueda,
            'usuario': usuario
        }
    )


def crear_permiso(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    if request.method == 'POST':

        nombre_permiso = request.POST.get('Nombre_permiso', '').strip()
        descripcion_permiso = request.POST.get('Descripcion_permiso', '').strip()

        if not nombre_permiso:

            messages.error(request, 'Debe ingresar el nombre del permiso.')

            return redirect('gestion_permisos')

        if Permisos.objects.filter(Nombre_permiso__iexact=nombre_permiso).exists():

            messages.error(request, 'Ya existe un permiso con ese nombre.')

            return redirect('gestion_permisos')

        Permisos.objects.create(
            Nombre_permiso=nombre_permiso,
            Descripcion_permiso=descripcion_permiso
        )

        messages.success(request, 'Permiso creado correctamente.')

    return redirect('gestion_permisos')


def editar_permiso(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    permiso = get_object_or_404(Permisos, ID_Permiso=pk)

    if request.method == 'POST':

        nombre_permiso = request.POST.get('Nombre_permiso', '').strip()
        descripcion_permiso = request.POST.get('Descripcion_permiso', '').strip()

        if not nombre_permiso:

            messages.error(request, 'Debe ingresar el nombre del permiso.')

            return redirect('gestion_permisos')

        existe = Permisos.objects.filter(
            Nombre_permiso__iexact=nombre_permiso
        ).exclude(
            ID_Permiso=pk
        ).exists()

        if existe:

            messages.error(request, 'Ya existe otro permiso con ese nombre.')

            return redirect('gestion_permisos')

        permiso.Nombre_permiso = nombre_permiso
        permiso.Descripcion_permiso = descripcion_permiso
        permiso.save()

        messages.success(request, 'Permiso modificado correctamente.')

    return redirect('gestion_permisos')


def eliminar_permiso(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    permiso = get_object_or_404(Permisos, ID_Permiso=pk)

    if request.method == 'POST':

        nombre_permiso = permiso.Nombre_permiso

        with transaction.atomic():

            PerfilesXPermisos.objects.filter(ID_Permiso=permiso).delete()

            permiso.delete()

        messages.success(
            request,
            f'El permiso "{nombre_permiso}" '
            f'fue eliminado correctamente.'
        )

    return redirect('gestion_permisos')


# ============================================================
# MIS PERMISOS
# ============================================================

def mis_permisos(request):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    if usuario.ID_Perfil.Nombre_perfil != 'Vendedor':
        return redirect('panel_principal')

    permisos = usuario.ID_Perfil.permisos.all()

    return render(
        request,
        'inventario/mis_permisos.html',
        {
            'usuario': usuario,
            'permisos': permisos,
        }
    )


# ============================================================
# PRODUCTOS
# ============================================================

def _leer_datos_producto(request, estado_por_defecto):
    """
    Lee y valida el formulario de producto (se usa al crear y al editar).
    Devuelve (datos, None) si está todo bien o (None, mensaje_de_error).
    """

    tipo_id = request.POST.get('ID_Tipo_producto')
    marca = request.POST.get('Marca', '').strip()
    nombre = request.POST.get('Nombre_producto', '').strip()
    descripcion = request.POST.get('Descripcion_producto', '').strip()
    precio = request.POST.get('Precio', '').strip()
    cantidad_presentacion = request.POST.get('Cantidad_presentacion', '').strip()
    unidad_medida = request.POST.get('Unidad_medida_producto', '').strip()
    estado_producto = request.POST.get('Estado_producto', estado_por_defecto)

    if not tipo_id:
        return None, 'Debe seleccionar un tipo de producto.'

    tipo = get_object_or_404(
        TiposProductos,
        ID_Tipo_producto=tipo_id,
        Estado_tipo_producto=True
    )

    if not nombre:
        return None, 'Debe ingresar el nombre del producto.'

    if not precio:
        return None, 'Debe ingresar el precio del producto.'

    try:
        precio = Decimal(precio)
    except (InvalidOperation, TypeError):
        return None, 'El precio ingresado no es válido.'

    if precio <= 0:
        return None, 'El precio debe ser mayor a cero.'

    if cantidad_presentacion:

        try:
            cantidad_presentacion = Decimal(cantidad_presentacion)
        except (InvalidOperation, TypeError):
            return None, 'La cantidad de presentación no es válida.'

        if cantidad_presentacion <= 0:
            return None, 'La cantidad de presentación debe ser mayor a cero.'

    else:

        cantidad_presentacion = None

    stock_minimo = request.POST.get('Stock_minimo', '').strip()

    if stock_minimo:

        try:
            stock_minimo = int(stock_minimo)
        except ValueError:
            return None, 'El stock mínimo ingresado no es válido.'

        if stock_minimo < 0:
            return None, 'El stock mínimo no puede ser negativo.'

    else:

        stock_minimo = None

    datos = {
        'stock_minimo': stock_minimo,
        'tipo': tipo,
        'marca': marca or None,
        'nombre': nombre,
        'descripcion': descripcion or None,
        'precio': precio,
        'cantidad_presentacion': cantidad_presentacion,
        'unidad_medida': unidad_medida or None,
        'estado_producto': estado_producto,
    }

    return datos, None


def _producto_duplicado(nombre, marca, excluir_pk=None):

    if marca:
        productos = Productos.objects.filter(
            Nombre_producto__iexact=nombre,
            Marca__iexact=marca
        )
    else:
        productos = Productos.objects.filter(
            Nombre_producto__iexact=nombre,
            Marca__isnull=True
        )

    if excluir_pk is not None:
        productos = productos.exclude(ID_Producto=excluir_pk)

    return productos.exists()


def _guardar_subtipos_producto(producto, ids):
    """
    Guarda los subtipos elegidos en el formulario.
    Solo actúa si el modelo Productos tiene una relación muchos a muchos
    llamada 'subtipos'; si no la tiene, no hace nada (no da error).
    """

    relacion = getattr(producto, 'subtipos', None)

    if relacion is None or not hasattr(relacion, 'set'):
        return

    ids_validos = [i for i in ids if str(i).isdigit()]

    relacion.set(Subtipos.objects.filter(ID_Subtipo__in=ids_validos))


def gestion_productos(request):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    busqueda = request.GET.get('q', '').strip()
    tipo_id = request.GET.get('tipo', '').strip()

    productos = Productos.objects.select_related(
        'ID_Tipo_producto',
        'stock'
    ).all()

    if busqueda:

        productos = productos.filter(
            Q(Nombre_producto__icontains=busqueda) |
            Q(Descripcion_producto__icontains=busqueda) |
            Q(Marca__icontains=busqueda)
        )

    if tipo_id:
        productos = productos.filter(ID_Tipo_producto_id=tipo_id)

    tipos_productos = TiposProductos.objects.filter(
        Estado_tipo_producto=True
    )

    return render(
        request,
        'inventario/productos.html',
        {
            'productos': productos,
            'tipos_productos': tipos_productos,
            'busqueda': busqueda,
            'usuario': usuario,
            'subtipos': Subtipos.objects.filter(
                Estado_subtipo=True
            ).select_related('ID_Tipo_producto').order_by('Nombre_subtipo'),
            'total_activos': Productos.objects.filter(Estado_producto='Activo').count(),
            'total_tipos': tipos_productos.count()
        }
    )


def crear_producto(request):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    if request.method == 'POST':

        datos, error = _leer_datos_producto(request, 'Activo')

        if error:

            messages.error(request, error)

            return redirect('gestion_productos')

        if _producto_duplicado(datos['nombre'], datos['marca']):

            messages.error(request, 'Ya existe un producto con esos datos.')

            return redirect('gestion_productos')

        with transaction.atomic():

            producto = Productos.objects.create(
                ID_Tipo_producto=datos['tipo'],
                Marca=datos['marca'],
                Nombre_producto=datos['nombre'],
                Descripcion_producto=datos['descripcion'],
                Precio=datos['precio'],
                Cantidad_presentacion=datos['cantidad_presentacion'],
                Unidad_medida_producto=datos['unidad_medida'],
                Estado_producto=datos['estado_producto']
            )

            # Stock inicial en 0; los ingresos se registran desde Lotes
            Stock.objects.get_or_create(
                ID_Producto=producto,
                defaults={
                    'Cantidad_stock': 0,
                    'Stock_minimo': datos['stock_minimo'] or 0
                }
            )

            _guardar_subtipos_producto(producto, request.POST.getlist('subtipos'))

        messages.success(request, 'Producto registrado correctamente.')

    return redirect('gestion_productos')


def editar_producto(request, pk):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    producto = get_object_or_404(Productos, ID_Producto=pk)

    if request.method == 'POST':

        datos, error = _leer_datos_producto(request, producto.Estado_producto)

        if error:

            messages.error(request, error)

            return redirect('gestion_productos')

        if _producto_duplicado(datos['nombre'], datos['marca'], excluir_pk=pk):

            messages.error(request, 'Ya existe otro producto con esos datos.')

            return redirect('gestion_productos')

        producto.ID_Tipo_producto = datos['tipo']
        producto.Marca = datos['marca']
        producto.Nombre_producto = datos['nombre']
        producto.Descripcion_producto = datos['descripcion']
        producto.Precio = datos['precio']
        producto.Cantidad_presentacion = datos['cantidad_presentacion']
        producto.Unidad_medida_producto = datos['unidad_medida']
        producto.Estado_producto = datos['estado_producto']

        with transaction.atomic():

            producto.save()

            if datos['stock_minimo'] is not None:

                stock, creado = Stock.objects.get_or_create(
                    ID_Producto=producto,
                    defaults={
                        'Cantidad_stock': 0,
                        'Stock_minimo': datos['stock_minimo']
                    }
                )

                if not creado:
                    stock.Stock_minimo = datos['stock_minimo']
                    stock.save()

            _guardar_subtipos_producto(producto, request.POST.getlist('subtipos'))

        messages.success(request, 'Producto actualizado correctamente.')

    return redirect('gestion_productos')


def cambiar_estado_producto(request, pk):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    producto = get_object_or_404(Productos, ID_Producto=pk)

    if request.method == 'POST':

        if producto.Estado_producto == 'Activo':

            producto.Estado_producto = 'Inactivo'

            messages.success(request, 'Producto dado de baja correctamente.')

        else:

            producto.Estado_producto = 'Activo'

            messages.success(request, 'Producto activado correctamente.')

        producto.save()

    return redirect('gestion_productos')


# ============================================================
# REGISTRAR INGRESO DE LOTE
# ============================================================

def registrar_ingreso_lote(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    # ------------------------------------------------------------
    # POST: registrar un lote nuevo
    # ------------------------------------------------------------
    if request.method == 'POST':

        proveedor_id = request.POST.get('ID_Proveedor')
        producto_id = request.POST.get('ID_Producto')
        numero_lote = request.POST.get('Numero_lote', '').strip()
        cantidad = request.POST.get('Cantidad_ingresada')
        fecha_ingreso = request.POST.get('Fecha_ingreso')
        fecha_vencimiento = request.POST.get('Fecha_vencimiento')

        if not proveedor_id or not producto_id:

            messages.error(request, 'Debe seleccionar el proveedor y el producto.')

            return redirect('registrar_ingreso_lote')

        if not numero_lote:

            messages.error(request, 'Debe ingresar el número de lote.')

            return redirect('registrar_ingreso_lote')

        try:
            cantidad = int(cantidad)
        except (TypeError, ValueError):

            messages.error(request, 'La cantidad ingresada no es válida.')

            return redirect('registrar_ingreso_lote')

        if cantidad <= 0:

            messages.error(request, 'La cantidad debe ser mayor a cero.')

            return redirect('registrar_ingreso_lote')

        if not fecha_ingreso:

            messages.error(request, 'Debe ingresar la fecha de ingreso.')

            return redirect('registrar_ingreso_lote')

        if fecha_vencimiento and fecha_vencimiento < fecha_ingreso:

            messages.error(
                request,
                'La fecha de vencimiento no puede ser anterior a la fecha de ingreso.'
            )

            return redirect('registrar_ingreso_lote')

        proveedor = get_object_or_404(
            Proveedores,
            ID_Proveedor=proveedor_id,
            estado_proveedor=True
        )

        producto = get_object_or_404(
            Productos,
            ID_Producto=producto_id,
            Estado_producto='Activo'
        )

        tipo_entrada = get_object_or_404(
            TiposMovimientos,
            Nombre_tipo_movimiento__iexact='Entrada'
        )

        lote_existente = Lotes.objects.filter(
            ID_Proveedor=proveedor,
            ID_Producto=producto,
            Numero_lote=numero_lote
        ).exists()

        if lote_existente:

            messages.error(request, 'Ya existe un lote con esos datos.')

            return redirect('registrar_ingreso_lote')

        # Lote + stock + movimiento se guardan juntos (todo o nada)
        with transaction.atomic():

            lote = Lotes.objects.create(
                ID_Proveedor=proveedor,
                ID_Producto=producto,
                Numero_lote=numero_lote,
                Cantidad_ingresada=cantidad,
                Cantidad_actual=cantidad,
                Fecha_ingreso=fecha_ingreso,
                Fecha_vencimiento=fecha_vencimiento or None
            )

            stock, creado = Stock.objects.select_for_update().get_or_create(
                ID_Producto=producto,
                defaults={
                    'Cantidad_stock': 0,
                    'Stock_minimo': 0
                }
            )

            stock.Cantidad_stock += cantidad
            stock.save()

            MovimientosStock.objects.create(
                ID_Usuario=usuario,
                ID_Tipo_movimiento=tipo_entrada,
                ID_Lote=lote,
                Cantidad_movimiento_stock=cantidad,
                Observaciones='Ingreso de lote'
            )

        messages.success(request, 'Ingreso de lote registrado correctamente.')

        return redirect('registrar_ingreso_lote')

    # ------------------------------------------------------------
    # GET: listado de lotes con buscador
    # ------------------------------------------------------------
    busqueda = request.GET.get('q', '').strip()

    lotes = Lotes.objects.select_related(
        'ID_Producto',
        'ID_Proveedor'
    ).order_by(
        '-Fecha_ingreso',
        '-ID_Lote'
    )

    if busqueda:

        lotes = lotes.filter(
            Q(Numero_lote__icontains=busqueda) |
            Q(ID_Producto__Nombre_producto__icontains=busqueda) |
            Q(ID_Proveedor__nombre_proveedor__icontains=busqueda)
        )

    productos = Productos.objects.filter(
        Estado_producto='Activo'
    ).order_by(
        'Nombre_producto'
    )

    proveedores = Proveedores.objects.filter(
        estado_proveedor=True
    ).order_by(
        'nombre_proveedor'
    )

    hoy = timezone.localdate()

    return render(
        request,
        'inventario/registrar_ingreso_lote.html',
        {
            'usuario': usuario,
            'lotes': lotes,
            'productos': productos,
            'proveedores': proveedores,
            'busqueda': busqueda,
            'hoy': hoy,
            'limite': hoy + timedelta(days=30),
        }
    )


# ============================================================
# MOVIMIENTOS DE STOCK
# ============================================================

def gestion_movimientos_stock(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()
    tipo_sel = request.GET.get('tipo', '').strip()

    movimientos = MovimientosStock.objects.select_related(
        'ID_Usuario',
        'ID_Tipo_movimiento',
        'ID_Lote',
        'ID_Lote__ID_Producto',
        'ID_Lote__ID_Proveedor'
    ).order_by(
        '-Fecha_hora_movimiento'
    )

    if busqueda:

        movimientos = movimientos.filter(
            Q(ID_Lote__ID_Producto__Nombre_producto__icontains=busqueda) |
            Q(ID_Lote__Numero_lote__icontains=busqueda) |
            Q(Observaciones__icontains=busqueda)
        )

    if tipo_sel:
        movimientos = movimientos.filter(ID_Tipo_movimiento_id=tipo_sel)

    # Para el filtro de la tabla: todos los tipos
    todos_tipos = TiposMovimientos.objects.all()

    # Para el modal "Registrar egreso": sin 'Entrada' (los ingresos se
    # registran desde Ingreso de Lote y generan su movimiento solos)
    tipos_movimientos = TiposMovimientos.objects.exclude(
        Nombre_tipo_movimiento__iexact='Entrada'
    )

    lotes = Lotes.objects.select_related(
        'ID_Producto',
        'ID_Proveedor'
    ).filter(
        Cantidad_actual__gt=0
    )

    return render(
        request,
        'inventario/movimientos_stock.html',
        {
            'movimientos': movimientos,
            'todos_tipos': todos_tipos,
            'tipos_movimientos': tipos_movimientos,
            'lotes': lotes,
            'busqueda': busqueda,
            'tipo_sel': tipo_sel,
            'usuario': usuario
        }
    )


def crear_movimiento_stock(request):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_movimientos_stock')

    tipo_id = request.POST.get('ID_Tipo_movimiento')
    lote_id = request.POST.get('ID_Lote')

    if not tipo_id or not lote_id:

        messages.error(request, 'Debe seleccionar el lote y el tipo de movimiento.')

        return redirect('gestion_movimientos_stock')

    tipo_movimiento = get_object_or_404(
        TiposMovimientos,
        ID_Tipo_movimiento=tipo_id
    )

    nombre_movimiento = tipo_movimiento.Nombre_tipo_movimiento.strip().lower()

    if nombre_movimiento == 'entrada':

        messages.error(
            request,
            'Los movimientos de entrada se registran mediante el ingreso de lote.'
        )

        return redirect('gestion_movimientos_stock')

    if nombre_movimiento not in ('salida por venta', 'salida por vencimiento'):

        messages.error(request, 'El tipo de movimiento no es válido.')

        return redirect('gestion_movimientos_stock')

    try:

        cantidad = int(
            request.POST.get(
                'Cantidad_movimiento_stock',
                request.POST.get('Cantidad', 0)
            )
        )

    except (TypeError, ValueError):

        messages.error(request, 'La cantidad ingresada no es válida.')

        return redirect('gestion_movimientos_stock')

    if cantidad <= 0:

        messages.error(request, 'La cantidad debe ser mayor a cero.')

        return redirect('gestion_movimientos_stock')

    observaciones = request.POST.get('Observaciones', '').strip()

    # CORREGIDO: el usuario del movimiento es el que tiene la sesión
    # iniciada (antes se tomaba de un campo del formulario), y todo el
    # descuento se hace en una transacción con las filas bloqueadas.
    with transaction.atomic():

        lote = get_object_or_404(
            Lotes.objects.select_for_update(),
            ID_Lote=lote_id
        )

        producto = lote.ID_Producto

        stock = get_object_or_404(
            Stock.objects.select_for_update(),
            ID_Producto=producto
        )

        if cantidad > lote.Cantidad_actual:

            messages.error(
                request,
                'No hay suficiente cantidad disponible en el lote seleccionado.'
            )

            return redirect('gestion_movimientos_stock')

        if cantidad > stock.Cantidad_stock:

            messages.error(request, 'No hay suficiente stock disponible.')

            return redirect('gestion_movimientos_stock')

        cantidad_anterior = stock.Cantidad_stock

        stock.Cantidad_stock -= cantidad
        stock.save()

        lote.Cantidad_actual -= cantidad
        lote.save()

        MovimientosStock.objects.create(
            ID_Usuario=usuario_admin,
            ID_Tipo_movimiento=tipo_movimiento,
            ID_Lote=lote,
            Cantidad_movimiento_stock=cantidad,
            Observaciones=observaciones or None
        )

        if (
            cantidad_anterior > stock.Stock_minimo
            and
            stock.Cantidad_stock <= stock.Stock_minimo
        ):

            Alertas.objects.create(
                ID_Lote=None,
                ID_Stock=stock,
                Tipo_alerta='Stock mínimo',
                Mensaje=(
                    f'El producto '
                    f'{producto.Nombre_producto} '
                    f'alcanzó el stock mínimo.'
                ),
                Cantidad_al_generar=stock.Cantidad_stock,
                Stock_minimo_al_generar=stock.Stock_minimo,
                Atendida=False
            )

    messages.success(request, 'Movimiento de stock registrado correctamente.')

    return redirect('gestion_movimientos_stock')


# ============================================================
# GENERAR ALERTAS DE VENCIMIENTO
# ============================================================

def generar_alertas_vencimiento():

    fecha_actual = timezone.now().date()

    fecha_limite = fecha_actual + timedelta(days=30)

    productos = Productos.objects.filter(
        lotes__Fecha_vencimiento__isnull=False,
        lotes__Fecha_vencimiento__gte=fecha_actual,
        lotes__Fecha_vencimiento__lte=fecha_limite
    ).distinct()

    for producto in productos:

        stock = getattr(producto, 'stock', None)

        if not stock:
            continue

        lotes = producto.lotes.filter(
            Fecha_vencimiento__isnull=False,
            Fecha_vencimiento__gte=fecha_actual,
            Fecha_vencimiento__lte=fecha_limite,
            Cantidad_actual__gt=0
        )

        for lote in lotes:

            dias_restantes = (lote.Fecha_vencimiento - fecha_actual).days

            existe_alerta = Alertas.objects.filter(
                ID_Lote=lote,
                ID_Stock=stock,
                Tipo_alerta='Vencimiento'
            ).exists()

            if not existe_alerta:

                Alertas.objects.create(
                    ID_Lote=lote,
                    ID_Stock=stock,
                    Tipo_alerta='Vencimiento',
                    Mensaje=(
                        f'El producto '
                        f'{producto.Nombre_producto} '
                        f'del lote {lote.Numero_lote} '
                        f'vence en {dias_restantes} días '
                        f'({lote.Fecha_vencimiento.strftime("%d/%m/%Y")}).'
                    ),
                    Cantidad_al_generar=lote.Cantidad_actual,
                    Stock_minimo_al_generar=stock.Stock_minimo,
                    Atendida=False
                )


# ============================================================
# HISTORIAL DE ALERTAS
# ============================================================

def gestion_alertas(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    generar_alertas_vencimiento()

    fecha = request.GET.get('fecha', '').strip()
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    usuario_id = request.GET.get('usuario', '').strip()
    tipo_alerta = request.GET.get('tipo', '').strip()
    producto_id = request.GET.get('producto', '').strip()
    stock_id = request.GET.get('stock', '').strip()

    alertas = Alertas.objects.select_related(
        'ID_Lote',
        'ID_Lote__ID_Producto',
        'ID_Lote__ID_Proveedor',
        'ID_Stock',
        'ID_Stock__ID_Producto',
        'ID_Usuario'
    ).all().order_by(
        '-Fecha_hora_historial_alerta'
    )

    if fecha:
        alertas = alertas.filter(Fecha_hora_historial_alerta__date=fecha)

    if fecha_desde:
        alertas = alertas.filter(Fecha_hora_historial_alerta__date__gte=fecha_desde)

    if fecha_hasta:
        alertas = alertas.filter(Fecha_hora_historial_alerta__date__lte=fecha_hasta)

    if usuario_id:
        alertas = alertas.filter(ID_Usuario_id=usuario_id)

    if tipo_alerta:
        alertas = alertas.filter(Tipo_alerta=tipo_alerta)

    if producto_id:
        alertas = alertas.filter(ID_Stock__ID_Producto_id=producto_id)

    if stock_id:
        alertas = alertas.filter(ID_Stock_id=stock_id)

    usuarios = Usuarios.objects.filter(
        Estado_usuario=True
    ).order_by(
        'Apellido_usuario',
        'Nombre_usuario'
    )

    productos = Productos.objects.filter(
        Estado_producto='Activo'
    ).order_by(
        'Nombre_producto'
    )

    stock = Stock.objects.select_related(
        'ID_Producto'
    ).all().order_by(
        'ID_Producto__Nombre_producto'
    )

    return render(
        request,
        'inventario/alertas.html',
        {
            'alertas': alertas,
            'usuarios': usuarios,
            'productos': productos,
            'stock': stock,
            'fecha': fecha,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'usuario_id': usuario_id,
            'tipo_alerta': tipo_alerta,
            'producto_id': producto_id,
            'stock_id': stock_id,
            'usuario': usuario
        }
    )