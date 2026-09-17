from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
import unicodedata

from .forms import ProveedorForm

from .models import (
    TiposProductos,
    Agroquimicos,
    Proveedores,
    TiposMovimientos,
    Perfiles,
    Permisos,
    PerfilesXPermisos,
    Usuarios,
    Productos,
    ProductosXAgroquimicos,
    ProductosXProveedores,
    Stock,
    Alertas,
    MovimientosStock
)


# ============================================================
# LOGIN
# ============================================================

def login_view(request):

    error_message = None

    if request.method == 'POST':

        usuario_input = request.POST.get(
            'usuario',
            ''
        ).strip()

        password_input = request.POST.get(
            'password',
            ''
        )

        try:

            usuario = Usuarios.objects.get(
                Usuario=usuario_input
            )

            # Verificar si el usuario está activo
            if not usuario.Estado_usuario:

                error_message = 'El usuario se encuentra inactivo.'

            # Verificar contraseña
            elif check_password(
                password_input,
                usuario.Contrasena
            ):

                # Guardar datos del usuario en la sesión
                request.session['usuario_id'] = usuario.ID_Usuario
                request.session['usuario_nombre'] = usuario.Usuario

                # Si debe cambiar la contraseña
                if usuario.Cambiar_contrasena:

                    return redirect(
                        'cambiar_contrasena'
                    )

                # Ingresar al panel
                return redirect(
                    'panel_principal'
                )

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


# ============================================================
# CAMBIAR CONTRASEÑA
# ============================================================

def cambiar_contrasena(request):

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:

        return redirect(
            'login'
        )

    usuario = get_object_or_404(
        Usuarios,
        ID_Usuario=usuario_id
    )

    error_message = None

    if request.method == 'POST':

        nueva_contrasena = request.POST.get(
            'nueva_contrasena',
            ''
        )

        confirmar_contrasena = request.POST.get(
            'confirmar_contrasena',
            ''
        )

        # Verificar que coincidan
        if nueva_contrasena != confirmar_contrasena:

            error_message = 'Las contraseñas no coinciden.'

        # Verificar longitud
        elif len(nueva_contrasena) < 8:

            error_message = (
                'La contraseña debe tener al menos 8 caracteres.'
            )

        else:

            usuario.Contrasena = make_password(
                nueva_contrasena
            )

            usuario.Cambiar_contrasena = False

            usuario.save()

            messages.success(
                request,
                'Contraseña actualizada correctamente.'
            )

            return redirect(
                'panel_principal'
            )

    return render(
        request,
        'inventario/cambiar_contrasena.html',
        {
            'error': error_message,
            'usuario': usuario
        }
    )


# ============================================================
# PANEL PRINCIPAL
# ============================================================

def panel_principal(request):

    usuario_id = request.session.get('usuario_id')

    if not usuario_id:
        return redirect('login')

    usuario = get_object_or_404(
        Usuarios.objects.select_related('ID_Perfil'),
        ID_Usuario=usuario_id
    )

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

def gestion_proveedores(request):

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    proveedores_list = Proveedores.objects.all()

    if busqueda:

        proveedores_list = proveedores_list.filter(
            Q(nombre_proveedor__icontains=busqueda) |
            Q(email_proveedor__icontains=busqueda) |
            Q(direccion_proveedor__icontains=busqueda)
        )

    activos_count = Proveedores.objects.filter(
        estado_proveedor=True
    ).count()

    total_count = Proveedores.objects.count()

    form = ProveedorForm()

    productos_list = Productos.objects.select_related(
        'ID_Tipo_producto'
    ).all()

    error_duplicado_id = request.session.pop(
        'error_duplicado_id',
        None
    )

    proveedor_conflicto = None

    if error_duplicado_id:

        proveedor_conflicto = Proveedores.objects.filter(
            pk=error_duplicado_id
        ).first()

    return render(
        request,
        'inventario/proveedores.html',
        {
            'proveedores': proveedores_list,
            'activos_count': activos_count,
            'total_count': total_count,
            'form': form,
            'productos_list': productos_list,
            'busqueda': busqueda,
            'proveedor_conflicto': proveedor_conflicto
        }
    )


def crear_proveedor(request):

    if request.method == 'POST':

        form = ProveedorForm(
            request.POST
        )

        nombre = request.POST.get(
            'nombre_proveedor',
            ''
        ).strip()

        telefono = request.POST.get(
            'telefono_proveedor',
            ''
        ).strip()

        email = request.POST.get(
            'email_proveedor',
            ''
        ).strip()

        direccion = request.POST.get(
            'direccion_proveedor',
            ''
        ).strip()

        query = Q()

        if nombre:

            query |= Q(
                nombre_proveedor__iexact=nombre
            )

        if telefono:

            query |= Q(
                telefono_proveedor__iexact=telefono
            )

        if email:

            query |= Q(
                email_proveedor__iexact=email
            )

        if direccion:

            query |= Q(
                direccion_proveedor__iexact=direccion
            )

        conflicto = (
            Proveedores.objects.filter(
                query
            ).first()
            if (
                nombre or
                telefono or
                email or
                direccion
            )
            else None
        )

        if conflicto:

            request.session[
                'error_duplicado_id'
            ] = conflicto.pk

            return redirect(
                'gestion_proveedores'
            )

        if form.is_valid():

            proveedor = form.save()

            productos_seleccionados = (
                form.cleaned_data.get(
                    'productos'
                )
            )

            if productos_seleccionados:

                for prod in productos_seleccionados:

                    ProductosXProveedores.objects.create(
                        ID_Producto=prod,
                        ID_Proveedor=proveedor
                    )

            messages.success(
                request,
                'Proveedor registrado con éxito.'
            )

            return redirect(
                'gestion_proveedores'
            )

    return redirect(
        'gestion_proveedores'
    )


def editar_proveedor(request, pk):

    proveedor = get_object_or_404(
        Proveedores,
        pk=pk
    )

    if request.method == 'POST':

        nombre = request.POST.get(
            'nombre_proveedor',
            ''
        ).strip()

        telefono = request.POST.get(
            'telefono_proveedor',
            ''
        ).strip()

        email = request.POST.get(
            'email_proveedor',
            ''
        ).strip()

        direccion = request.POST.get(
            'direccion_proveedor',
            ''
        ).strip()

        query = Q()

        if nombre:

            query |= Q(
                nombre_proveedor__iexact=nombre
            )

        if telefono:

            query |= Q(
                telefono_proveedor__iexact=telefono
            )

        if email:

            query |= Q(
                email_proveedor__iexact=email
            )

        if direccion:

            query |= Q(
                direccion_proveedor__iexact=direccion
            )

        conflicto = (
            Proveedores.objects
            .filter(query)
            .exclude(pk=pk)
            .first()
            if (
                nombre or
                telefono or
                email or
                direccion
            )
            else None
        )

        if conflicto:

            request.session[
                'error_duplicado_id'
            ] = conflicto.pk

            return redirect(
                'gestion_proveedores'
            )

        proveedor.nombre_proveedor = nombre

        proveedor.telefono_proveedor = request.POST.get(
            'telefono_proveedor'
        )

        proveedor.email_proveedor = email

        proveedor.direccion_proveedor = request.POST.get(
            'direccion_proveedor'
        )

        estado_val = request.POST.get(
            'estado_proveedor'
        )

        proveedor.estado_proveedor = (
            True
            if estado_val in [
                'True',
                'true',
                '1',
                True
            ]
            else False
        )

        proveedor.save(
            update_fields=[
                'nombre_proveedor',
                'telefono_proveedor',
                'email_proveedor',
                'direccion_proveedor',
                'estado_proveedor'
            ]
        )

        messages.success(
            request,
            'Proveedor actualizado correctamente.'
        )

    return redirect(
        'gestion_proveedores'
    )


def cambiar_estado_proveedor(request, pk):

    if request.method == 'POST':

        proveedor = get_object_or_404(
            Proveedores,
            pk=pk
        )

        estado = request.POST.get(
            'estado'
        )

        if estado == 'inactivo':

            proveedor.estado_proveedor = False

        elif estado == 'activo':

            proveedor.estado_proveedor = True

        proveedor.save(
            update_fields=[
                'estado_proveedor'
            ]
        )

        if proveedor.estado_proveedor:

            messages.success(
                request,
                f'El proveedor {proveedor.nombre_proveedor} '
                f'ha sido activado.'
            )

        else:

            messages.warning(
                request,
                f'El proveedor {proveedor.nombre_proveedor} '
                f'ha sido dado de baja.'
            )

    return redirect(
        'gestion_proveedores'
    )


# ============================================================
# TIPOS DE PRODUCTOS
# ============================================================

def gestion_tipos_productos(request):

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    tipos = TiposProductos.objects.all()

    if busqueda:

        tipos = tipos.filter(
            Nombre_tipo_producto__icontains=busqueda
        )

    return render(
        request,
        'inventario/tipos_productos.html',
        {
            'tipos_productos': tipos,
            'busqueda': busqueda
        }
    )


def crear_tipo_producto(request):

    if request.method == 'POST':

        nombre = request.POST.get(
            'Nombre_tipo_producto',
            ''
        ).strip()

        if nombre:

            TiposProductos.objects.create(
                Nombre_tipo_producto=nombre
            )

            messages.success(
                request,
                'Tipo de producto registrado correctamente.'
            )

    return redirect(
        'gestion_tipos_productos'
    )


def editar_tipo_producto(request, pk):

    tipo = get_object_or_404(
        TiposProductos,
        pk=pk
    )

    if request.method == 'POST':

        tipo.Nombre_tipo_producto = request.POST.get(
            'Nombre_tipo_producto',
            ''
        ).strip()

        tipo.save()

        messages.success(
            request,
            'Tipo de producto actualizado correctamente.'
        )

    return redirect(
        'gestion_tipos_productos'
    )


# ============================================================
# AGROQUÍMICOS
# ============================================================

def gestion_agroquimicos(request):

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    agroquimicos = Agroquimicos.objects.all()

    if busqueda:

        agroquimicos = agroquimicos.filter(
            Q(Nombre_agroquimico__icontains=busqueda) |
            Q(Descripcion_agroquimico__icontains=busqueda)
        )

    return render(
        request,
        'inventario/agroquimicos.html',
        {
            'agroquimicos': agroquimicos,
            'busqueda': busqueda
        }
    )


def crear_agroquimico(request):

    if request.method == 'POST':

        nombre = request.POST.get(
            'Nombre_agroquimico',
            ''
        ).strip()

        descripcion = request.POST.get(
            'Descripcion_agroquimico',
            ''
        ).strip()

        if nombre:

            Agroquimicos.objects.create(
                Nombre_agroquimico=nombre,
                Descripcion_agroquimico=descripcion
            )

            messages.success(
                request,
                'Agroquímico registrado correctamente.'
            )

    return redirect(
        'gestion_agroquimicos'
    )


def editar_agroquimico(request, pk):

    agroquimico = get_object_or_404(
        Agroquimicos,
        pk=pk
    )

    if request.method == 'POST':

        agroquimico.Nombre_agroquimico = request.POST.get(
            'Nombre_agroquimico',
            ''
        ).strip()

        agroquimico.Descripcion_agroquimico = request.POST.get(
            'Descripcion_agroquimico',
            ''
        ).strip()

        agroquimico.save()

        messages.success(
            request,
            'Agroquímico actualizado correctamente.'
        )

    return redirect(
        'gestion_agroquimicos'
    )


# ============================================================
# GESTIONAR USUARIOS
# ============================================================

def gestion_usuarios(request):

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    usuarios = Usuarios.objects.select_related(
        'ID_Perfil'
    ).all()

    if busqueda:

        filtros = (
            Q(Nombre_usuario__icontains=busqueda) |
            Q(Apellido_usuario__icontains=busqueda) |
            Q(Usuario__icontains=busqueda) |
            Q(Email_usuario__icontains=busqueda)
        )

        if busqueda.isdigit():

            filtros |= Q(
                DNI=int(busqueda)
            )

        usuarios = usuarios.filter(
            filtros
        )

    perfiles = Perfiles.objects.all()

    return render(
        request,
        'inventario/usuarios.html',
        {
            'usuarios': usuarios,
            'perfiles': perfiles,
            'busqueda': busqueda
        }
    )


# ============================================================
# CREAR USUARIO
# ============================================================

def crear_usuario(request):

    if request.method == 'POST':

        perfil_id = request.POST.get(
            'ID_Perfil'
        )

        perfil = get_object_or_404(
            Perfiles,
            pk=perfil_id
        )

        dni = request.POST.get(
            'DNI',
            ''
        ).strip()

        apellido = request.POST.get(
            'Apellido_usuario',
            ''
        ).strip()

        nombre = request.POST.get(
            'Nombre_usuario',
            ''
        ).strip()

        email = request.POST.get(
            'Email_usuario',
            ''
        ).strip()

        contrasena = request.POST.get(
            'Contrasena',
            ''
        ).strip()

        # Validar contraseña
        if len(contrasena) < 8:

            messages.error(
                request,
                'La contraseña debe tener al menos 8 caracteres.'
            )

            return redirect(
                'gestion_usuarios'
            )

        # Generar usuario automáticamente
        apellido_sin_tildes = ''.join(
            caracter
            for caracter in unicodedata.normalize(
                'NFD',
                apellido
            )
            if unicodedata.category(caracter) != 'Mn'
        )

        nombre_sin_tildes = ''.join(
            caracter
            for caracter in unicodedata.normalize(
                'NFD',
                nombre
            )
            if unicodedata.category(caracter) != 'Mn'
        )

        usuario_generado = (
            apellido_sin_tildes
            + nombre_sin_tildes[0]
        ).lower()

        # Verificar usuario existente
        if Usuarios.objects.filter(
            Usuario=usuario_generado
        ).exists():

            messages.error(
                request,
                f'El usuario {usuario_generado} ya existe.'
            )

            return redirect(
                'gestion_usuarios'
            )

        # Crear usuario
        usuario = Usuarios.objects.create(
            ID_Perfil=perfil,
            DNI=dni,
            Apellido_usuario=apellido,
            Nombre_usuario=nombre,
            Usuario=usuario_generado,
            Contrasena=make_password(
                contrasena
            ),
            Email_usuario=email,
            Estado_usuario=True,
            Cambiar_contrasena=True
        )

        messages.success(
            request,
            f'El usuario {usuario.Usuario} '
            f'ha sido registrado correctamente. '
            f'Deberá cambiar su contraseña '
            f'en el próximo inicio de sesión.'
        )

    return redirect(
        'gestion_usuarios'
    )


# ============================================================
# EDITAR USUARIO
# ============================================================

def editar_usuario(request, pk):

    usuario = get_object_or_404(
        Usuarios,
        ID_Usuario=pk
    )

    if request.method == 'POST':

        nuevo_email = request.POST.get(
            'Email_usuario',
            ''
        ).strip()

        if not nuevo_email:

            messages.error(
                request,
                'El correo electrónico es obligatorio.'
            )

            return render(
                request,
                'inventario/editar_usuario.html',
                {
                    'usuario': usuario
                }
            )

        usuario.Email_usuario = nuevo_email

        usuario.save()

        messages.success(
            request,
            f'El usuario {usuario.Usuario} '
            f'ha sido modificado correctamente.'
        )

        return redirect(
            'gestion_usuarios'
        )

    return render(
        request,
        'inventario/editar_usuario.html',
        {
            'usuario': usuario
        }
    )


# ============================================================
# DAR DE BAJA USUARIO
# ============================================================

def dar_baja_usuario(request, pk):

    usuario = get_object_or_404(
        Usuarios,
        pk=pk
    )

    if request.method == 'POST':

        usuario.Estado_usuario = False

        usuario.Fecha_Baja = timezone.now().date()

        usuario.save()

        messages.success(
            request,
            'Usuario dado de baja correctamente.'
        )

    return redirect(
        'gestion_usuarios'
    )


# ============================================================
# RESTABLECER CONTRASEÑA
# ============================================================

def restablecer_contrasena(request, pk):

    usuario = get_object_or_404(
        Usuarios,
        pk=pk
    )

    if request.method == 'POST':

        nueva_contrasena = request.POST.get(
            'nueva_contrasena',
            ''
        )

        confirmar_contrasena = request.POST.get(
            'confirmar_contrasena',
            ''
        )

        if nueva_contrasena != confirmar_contrasena:

            messages.error(
                request,
                'Las contraseñas no coinciden.'
            )

            return render(
                request,
                'inventario/restablecer_contrasena.html',
                {
                    'usuario': usuario
                }
            )

        if len(nueva_contrasena) < 8:

            messages.error(
                request,
                'La contraseña debe tener al menos 8 caracteres.'
            )

            return render(
                request,
                'inventario/restablecer_contrasena.html',
                {
                    'usuario': usuario
                }
            )

        usuario.Contrasena = make_password(
            nueva_contrasena
        )

        usuario.Cambiar_contrasena = True

        usuario.save()

        messages.success(
            request,
            f'La contraseña del usuario {usuario.Usuario} '
            'fue restablecida correctamente. '
            'Deberá cambiarla en el próximo inicio de sesión.'
        )

        return redirect(
            'gestion_usuarios'
        )

    return render(
        request,
        'inventario/restablecer_contrasena.html',
        {
            'usuario': usuario
        }
    )


# ============================================================
# GESTIÓN DE PERFILES
# ============================================================

def gestion_perfiles(request):

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    perfiles = Perfiles.objects.prefetch_related(
        'permisos'
    ).all()

    if busqueda:

        perfiles = perfiles.filter(
            Nombre_perfil__icontains=busqueda
        )

    permisos = Permisos.objects.all()

    return render(
        request,
        'inventario/perfiles.html',
        {
            'perfiles': perfiles,
            'permisos': permisos,
            'busqueda': busqueda
        }
    )


def crear_perfil(request):

    if request.method == 'POST':

        nombre_perfil = request.POST.get(
            'Nombre_perfil',
            ''
        ).strip()

        if not nombre_perfil:

            messages.error(
                request,
                'Debe ingresar el nombre del perfil.'
            )

            return redirect(
                'gestion_perfiles'
            )

        perfil_existente = Perfiles.objects.filter(
            Nombre_perfil__iexact=nombre_perfil
        ).exists()

        if perfil_existente:

            messages.error(
                request,
                'Ya existe un perfil con ese nombre.'
            )

            return redirect(
                'gestion_perfiles'
            )

        perfil = Perfiles.objects.create(
            Nombre_perfil=nombre_perfil
        )

        permisos_ids = request.POST.getlist(
            'permisos'
        )

        for permiso_id in permisos_ids:

            permiso = get_object_or_404(
                Permisos,
                ID_Permiso=permiso_id
            )

            PerfilesXPermisos.objects.create(
                ID_Perfil=perfil,
                ID_Permiso=permiso
            )

        messages.success(
            request,
            'Perfil creado correctamente.'
        )

    return redirect(
        'gestion_perfiles'
    )


def editar_perfil(request, pk):

    perfil = get_object_or_404(
        Perfiles,
        ID_Perfil=pk
    )

    if request.method == 'POST':

        nombre_perfil = request.POST.get(
            'Nombre_perfil',
            ''
        ).strip()

        if not nombre_perfil:

            messages.error(
                request,
                'Debe ingresar el nombre del perfil.'
            )

            return redirect(
                'gestion_perfiles'
            )

        perfil_existente = Perfiles.objects.filter(
            Nombre_perfil__iexact=nombre_perfil
        ).exclude(
            ID_Perfil=pk
        ).exists()

        if perfil_existente:

            messages.error(
                request,
                'Ya existe otro perfil con ese nombre.'
            )

            return redirect(
                'gestion_perfiles'
            )

        perfil.Nombre_perfil = nombre_perfil

        perfil.save()

        # Eliminar permisos anteriores
        PerfilesXPermisos.objects.filter(
            ID_Perfil=perfil
        ).delete()

        # Obtener permisos nuevos
        permisos_ids = request.POST.getlist(
            'permisos'
        )

        # Guardar permisos
        for permiso_id in permisos_ids:

            permiso = get_object_or_404(
                Permisos,
                ID_Permiso=permiso_id
            )

            PerfilesXPermisos.objects.create(
                ID_Perfil=perfil,
                ID_Permiso=permiso
            )

        messages.success(
            request,
            'Perfil actualizado correctamente.'
        )

    return redirect(
        'gestion_perfiles'
    )


def eliminar_perfil(request, pk):

    perfil = get_object_or_404(
        Perfiles,
        ID_Perfil=pk
    )

    if request.method == 'POST':

        # Verificar si está siendo utilizado
        if Usuarios.objects.filter(
            ID_Perfil=perfil
        ).exists():

            messages.error(
                request,
                'No se puede eliminar el perfil porque está siendo utilizado por un usuario.'
            )

            return redirect(
                'gestion_perfiles'
            )

        # Eliminar relaciones
        PerfilesXPermisos.objects.filter(
            ID_Perfil=perfil
        ).delete()

        # Eliminar perfil
        perfil.delete()

        messages.success(
            request,
            'Perfil eliminado correctamente.'
        )

    return redirect(
        'gestion_perfiles'
    )


# ============================================================
# GESTIÓN DE PERMISOS
# ============================================================

def gestion_permisos(request):

    if request.method == 'POST':

        nombre_permiso = request.POST.get(
            'Nombre_permiso',
            ''
        ).strip()

        descripcion_permiso = request.POST.get(
            'Descripcion_permiso',
            ''
        ).strip()

        if not nombre_permiso:
            messages.error(
                request,
                'Debe ingresar el nombre del permiso.'
            )
            return redirect(
                'gestion_permisos'
            )

        permiso_existente = Permisos.objects.filter(
            Nombre_permiso__iexact=nombre_permiso
        ).exists()

        if permiso_existente:
            messages.error(
                request,
                'Ya existe un permiso con ese nombre.'
            )
            return redirect(
                'gestion_permisos'
            )

        Permisos.objects.create(
            Nombre_permiso=nombre_permiso,
            Descripcion_permiso=descripcion_permiso
        )

        messages.success(
            request,
            'Permiso creado correctamente.'
        )

        return redirect(
            'gestion_permisos'
        )

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    permisos = Permisos.objects.prefetch_related(
        'perfiles'
    ).all()

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
            'busqueda': busqueda
        }
    )


# ============================================================
# CREAR PERMISO
# ============================================================

def crear_permiso(request):
    if request.method == 'POST':
        nombre_permiso = request.POST.get(
            'Nombre_permiso',
            ''
        ).strip()

        descripcion_permiso = request.POST.get(
            'Descripcion_permiso',
            ''
        ).strip()

        if not nombre_permiso:
            messages.error(
                request,
                'Debe ingresar el nombre del permiso.'
            )
            return redirect(
                'gestion_permisos'
            )

        permiso_existente = Permisos.objects.filter(
            Nombre_permiso__iexact=nombre_permiso
        ).exists()

        if permiso_existente:
            messages.error(
                request,
                'Ya existe un permiso con ese nombre.'
            )
            return redirect(
                'gestion_permisos'
            )

        Permisos.objects.create(
            Nombre_permiso=nombre_permiso,
            Descripcion_permiso=descripcion_permiso
        )

        messages.success(
            request,
            'Permiso creado correctamente.'
        )

    return redirect(
        'gestion_permisos'
    )


# ============================================================
# EDITAR PERMISO
# ============================================================

def editar_permiso(request, pk):

    permiso = get_object_or_404(
        Permisos,
        ID_Permiso=pk
    )

    if request.method == 'POST':

        nombre_permiso = request.POST.get(
            'Nombre_permiso',
            ''
        ).strip()

        descripcion_permiso = request.POST.get(
            'Descripcion_permiso',
            ''
        ).strip()

        if not nombre_permiso:
            messages.error(
                request,
                'Debe ingresar el nombre del permiso.'
            )
            return redirect(
                'gestion_permisos'
            )

        permiso_existente = Permisos.objects.filter(
            Nombre_permiso__iexact=nombre_permiso
        ).exclude(
            ID_Permiso=pk
        ).exists()

        if permiso_existente:
            messages.error(
                request,
                'Ya existe otro permiso con ese nombre.'
            )
            return redirect(
                'gestion_permisos'
            )

        permiso.Nombre_permiso = nombre_permiso
        permiso.Descripcion_permiso = descripcion_permiso

        permiso.save()

        messages.success(
            request,
            'Permiso modificado correctamente.'
        )

    return redirect(
        'gestion_permisos'
    )


# ============================================================
# ELIMINAR PERMISO
# ============================================================

def eliminar_permiso(request, pk):

    permiso = get_object_or_404(
        Permisos,
        ID_Permiso=pk
    )

    if request.method == 'POST':

        nombre_permiso = permiso.Nombre_permiso

        # Quitar el permiso de todos los perfiles
        PerfilesXPermisos.objects.filter(
            ID_Permiso=permiso
        ).delete()

        # Eliminar permiso
        permiso.delete()

        messages.success(
            request,
            f'El permiso "{nombre_permiso}" '
            f'fue eliminado correctamente.'
        )

    return redirect(
        'gestion_permisos'
    )


# ============================================================
# TIPOS DE MOVIMIENTOS
# ============================================================

def gestion_tipos_movimientos(request):

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    tipos = TiposMovimientos.objects.all()

    if busqueda:

        tipos = tipos.filter(
            Nombre_tipo_movimiento__icontains=busqueda
        )

    return render(
        request,
        'inventario/tipos_movimientos.html',
        {
            'tipos_movimientos': tipos,
            'busqueda': busqueda
        }
    )


def crear_tipo_movimiento(request):

    if request.method == 'POST':

        nombre = request.POST.get(
            'Nombre_tipo_movimiento',
            ''
        ).strip()

        if nombre:

            TiposMovimientos.objects.create(
                Nombre_tipo_movimiento=nombre
            )

            messages.success(
                request,
                'Tipo de movimiento registrado correctamente.'
            )

    return redirect(
        'gestion_tipos_movimientos'
    )


def editar_tipo_movimiento(request, pk):

    tipo = get_object_or_404(
        TiposMovimientos,
        pk=pk
    )

    if request.method == 'POST':

        tipo.Nombre_tipo_movimiento = request.POST.get(
            'Nombre_tipo_movimiento',
            ''
        ).strip()

        tipo.save()

        messages.success(
            request,
            'Tipo de movimiento actualizado correctamente.'
        )

    return redirect(
        'gestion_tipos_movimientos'
    )


# ============================================================
# PRODUCTOS
# ============================================================

def gestion_productos(request):

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    productos = Productos.objects.select_related(
        'ID_Tipo_producto'
    ).prefetch_related(
        'agroquimicos',
        'proveedores'
    ).all()

    if busqueda:

        productos = productos.filter(
            Q(Nombre_producto__icontains=busqueda) |
            Q(Descripcion_producto__icontains=busqueda)
        )

    tipos_productos = TiposProductos.objects.all()

    agroquimicos = Agroquimicos.objects.all()

    proveedores = Proveedores.objects.filter(
        estado_proveedor=True
    )

    return render(
        request,
        'inventario/productos.html',
        {
            'productos': productos,
            'tipos_productos': tipos_productos,
            'agroquimicos': agroquimicos,
            'proveedores': proveedores,
            'busqueda': busqueda
        }
    )


def crear_producto(request):

    if request.method == 'POST':

        tipo_id = request.POST.get(
            'ID_Tipo_producto'
        )

        tipo = get_object_or_404(
            TiposProductos,
            pk=tipo_id
        )

        producto = Productos.objects.create(
            ID_Tipo_producto=tipo,
            Nombre_producto=request.POST.get(
                'Nombre_producto',
                ''
            ).strip(),
            Descripcion_producto=request.POST.get(
                'Descripcion_producto',
                ''
            ).strip(),
            Fecha_vencimiento=request.POST.get(
                'Fecha_vencimiento'
            ) or None,
            Precio=request.POST.get(
                'Precio'
            )
        )

        agroquimicos_ids = request.POST.getlist(
            'agroquimicos'
        )

        for agro_id in agroquimicos_ids:

            agro = get_object_or_404(
                Agroquimicos,
                pk=agro_id
            )

            ProductosXAgroquimicos.objects.get_or_create(
                ID_Producto=producto,
                ID_Agroquimico=agro
            )

        proveedores_ids = request.POST.getlist(
            'proveedores'
        )

        for proveedor_id in proveedores_ids:

            proveedor = get_object_or_404(
                Proveedores,
                pk=proveedor_id
            )

            ProductosXProveedores.objects.get_or_create(
                ID_Producto=producto,
                ID_Proveedor=proveedor
            )

        messages.success(
            request,
            'Producto registrado correctamente.'
        )

    return redirect(
        'gestion_productos'
    )


def editar_producto(request, pk):

    producto = get_object_or_404(
        Productos,
        pk=pk
    )

    if request.method == 'POST':

        tipo_id = request.POST.get(
            'ID_Tipo_producto'
        )

        producto.ID_Tipo_producto = get_object_or_404(
            TiposProductos,
            pk=tipo_id
        )

        producto.Nombre_producto = request.POST.get(
            'Nombre_producto',
            ''
        ).strip()

        producto.Descripcion_producto = request.POST.get(
            'Descripcion_producto',
            ''
        ).strip()

        producto.Fecha_vencimiento = request.POST.get(
            'Fecha_vencimiento'
        ) or None

        producto.Precio = request.POST.get(
            'Precio'
        )

        producto.save()

        ProductosXAgroquimicos.objects.filter(
            ID_Producto=producto
        ).delete()

        for agro_id in request.POST.getlist(
            'agroquimicos'
        ):

            ProductosXAgroquimicos.objects.create(
                ID_Producto=producto,
                ID_Agroquimico_id=agro_id
            )

        ProductosXProveedores.objects.filter(
            ID_Producto=producto
        ).delete()

        for proveedor_id in request.POST.getlist(
            'proveedores'
        ):

            ProductosXProveedores.objects.create(
                ID_Producto=producto,
                ID_Proveedor_id=proveedor_id
            )

        messages.success(
            request,
            'Producto actualizado correctamente.'
        )

    return redirect(
        'gestion_productos'
    )


# ============================================================
# PRODUCTOS POR PROVEEDOR
# ============================================================

def gestion_productos_proveedores(request):

    relaciones = ProductosXProveedores.objects.select_related(
        'ID_Producto',
        'ID_Proveedor'
    ).all()

    return render(
        request,
        'inventario/productos_proveedores.html',
        {
            'relaciones': relaciones
        }
    )


# ============================================================
# STOCK
# ============================================================

def gestion_stock(request):

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    stock = Stock.objects.select_related(
        'ID_Producto'
    ).all()

    if busqueda:

        stock = stock.filter(
            ID_Producto__Nombre_producto__icontains=busqueda
        )

    productos = Productos.objects.all()

    return render(
        request,
        'inventario/stock.html',
        {
            'stock': stock,
            'productos': productos,
            'busqueda': busqueda
        }
    )


def crear_stock(request):

    if request.method == 'POST':

        producto_id = request.POST.get(
            'ID_Producto'
        )

        producto = get_object_or_404(
            Productos,
            pk=producto_id
        )

        Stock.objects.create(
            ID_Producto=producto,
            Cantidad_stock=request.POST.get(
                'Cantidad_stock'
            ),
            Stock_minimo=request.POST.get(
                'Stock_minimo'
            )
        )

        messages.success(
            request,
            'Stock registrado correctamente.'
        )

    return redirect(
        'gestion_stock'
    )


def editar_stock(request, pk):

    stock = get_object_or_404(
        Stock,
        pk=pk
    )

    if request.method == 'POST':

        stock.Cantidad_stock = request.POST.get(
            'Cantidad_stock'
        )

        stock.Stock_minimo = request.POST.get(
            'Stock_minimo'
        )

        stock.save()

        messages.success(
            request,
            'Stock actualizado correctamente.'
        )

    return redirect(
        'gestion_stock'
    )


# ============================================================
# MOVIMIENTOS DE STOCK
# ============================================================

def gestion_movimientos_stock(request):

    movimientos = MovimientosStock.objects.select_related(
        'ID_Usuario',
        'ID_Tipo_movimiento',
        'ID_Stock',
        'ID_Stock__ID_Producto'
    ).all().order_by(
        '-Fecha_hora_movimiento'
    )

    usuarios = Usuarios.objects.all()

    tipos_movimientos = TiposMovimientos.objects.all()

    stock = Stock.objects.select_related(
        'ID_Producto'
    ).all()

    return render(
        request,
        'inventario/movimientos_stock.html',
        {
            'movimientos': movimientos,
            'usuarios': usuarios,
            'tipos_movimientos': tipos_movimientos,
            'stock': stock
        }
    )


def crear_movimiento_stock(request):

    if request.method == 'POST':

        usuario = get_object_or_404(
            Usuarios,
            pk=request.POST.get(
                'ID_Usuario'
            )
        )

        tipo_movimiento = get_object_or_404(
            TiposMovimientos,
            pk=request.POST.get(
                'ID_Tipo_movimiento'
            )
        )

        stock = get_object_or_404(
            Stock,
            pk=request.POST.get(
                'ID_Stock'
            )
        )

        cantidad = int(
            request.POST.get(
                'Cantidad',
                0
            )
        )

        MovimientosStock.objects.create(
            ID_Usuario=usuario,
            ID_Tipo_movimiento=tipo_movimiento,
            ID_Stock=stock,
            Cantidad=cantidad
        )

        messages.success(
            request,
            'Movimiento de stock registrado correctamente.'
        )

    return redirect(
        'gestion_movimientos_stock'
    )


# ============================================================
# ALERTAS
# ============================================================

def gestion_alertas(request):

    alertas = Alertas.objects.select_related(
        'ID_Stock',
        'ID_Stock__ID_Producto'
    ).all().order_by(
        '-Fecha_hora_alerta'
    )

    return render(
        request,
        'inventario/alertas.html',
        {
            'alertas': alertas
        }
    )