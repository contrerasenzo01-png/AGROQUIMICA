from django.shortcuts import render, redirect, get_object_or_404

from django.db.models import Q

from django.contrib import messages

from django.utils import timezone

from django.contrib.auth.hashers import make_password, check_password

import unicodedata

from datetime import timedelta

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
# CONTROL DE ACCESO
# ============================================================

def usuario_es_administrador(request):
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

    if not usuario.ID_Perfil:
        return None

    if usuario.ID_Perfil.Nombre_perfil != 'Administrador':
        return None

    return usuario


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

            usuario = Usuarios.objects.select_related(
                'ID_Perfil'
            ).get(
                Usuario=usuario_input
            )

            if not usuario.Estado_usuario:

                error_message = (
                    'El usuario se encuentra inactivo.'
                )

            elif not usuario.ID_Perfil:

                error_message = (
                    'El usuario no tiene un perfil asignado.'
                )

            elif not usuario.ID_Perfil.Estado_perfil:

                error_message = (
                    'El perfil del usuario se encuentra inactivo.'
                )

            elif check_password(
                password_input,
                usuario.Contrasena
            ):

                request.session['usuario_id'] = (
                    usuario.ID_Usuario
                )

                request.session['usuario_nombre'] = (
                    usuario.Usuario
                )

                request.session['perfil_id'] = (
                    usuario.ID_Perfil.ID_Perfil
                )

                request.session['perfil_nombre'] = (
                    usuario.ID_Perfil.Nombre_perfil
                )

                if usuario.Cambiar_contrasena:

                    return redirect(
                        'cambiar_contrasena'
                    )

                return redirect(
                    'panel_principal'
                )

            else:

                error_message = (
                    'Usuario o contraseña incorrectos.'
                )

        except Usuarios.DoesNotExist:

            error_message = (
                'Usuario o contraseña incorrectos.'
            )

    return render(
        request,
        'inventario/login.html',
        {
            'error': error_message
        }
    )


def cerrar_sesion(request):

    request.session.flush()

    return redirect(
        'login'
    )


# ============================================================
# PANEL PRINCIPAL
# ============================================================

def panel_principal(request):

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:

        return redirect(
            'login'
        )

    generar_alertas_vencimiento()

    usuario = get_object_or_404(
        Usuarios.objects.select_related(
            'ID_Perfil'
        ),
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

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    proveedores = Proveedores.objects.all()

    if busqueda:

        proveedores = proveedores.filter(
            Q(nombre_proveedor__icontains=busqueda) |
            Q(email_proveedor__icontains=busqueda) |
            Q(direccion_proveedor__icontains=busqueda)
        )

    total_proveedores = Proveedores.objects.count()

    proveedores_activos = Proveedores.objects.filter(
        estado_proveedor=True
    ).count()

    form = ProveedorForm()

    error_duplicado_id = request.session.pop(
        'error_duplicado_id',
        None
    )

    proveedor_conflicto = request.session.pop(
        'proveedor_conflicto',
        None
    )

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

            nombre = form.cleaned_data[
                'nombre_proveedor'
            ].strip()

            telefono = form.cleaned_data[
                'telefono_proveedor'
            ].strip()

            email = form.cleaned_data[
                'email_proveedor'
            ].strip()

            direccion = form.cleaned_data[
                'direccion_proveedor'
            ].strip()

            proveedor_existente = Proveedores.objects.filter(

                Q(nombre_proveedor__iexact=nombre) |

                Q(telefono_proveedor=telefono) |

                Q(email_proveedor__iexact=email) |

                Q(direccion_proveedor__iexact=direccion)

            ).first()

            if proveedor_existente:

                request.session[
                    'error_duplicado_id'
                ] = proveedor_existente.ID_Proveedor

                request.session[
                    'proveedor_conflicto'
                ] = (
                    'Ya existe un proveedor con alguno de los datos ingresados.'
                )

                return redirect(
                    'gestion_proveedores'
                )

            form.save()

            return redirect(
                'gestion_proveedores'
            )

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

    proveedor = get_object_or_404(
        Proveedores,
        ID_Proveedor=pk
    )

    if request.method == 'POST':

        form = ProveedorForm(
            request.POST,
            instance=proveedor
        )

        if form.is_valid():

            nombre = form.cleaned_data[
                'nombre_proveedor'
            ].strip()

            telefono = form.cleaned_data[
                'telefono_proveedor'
            ].strip()

            email = form.cleaned_data[
                'email_proveedor'
            ].strip()

            direccion = form.cleaned_data[
                'direccion_proveedor'
            ].strip()

            proveedor_existente = Proveedores.objects.filter(

                Q(nombre_proveedor__iexact=nombre) |

                Q(telefono_proveedor=telefono) |

                Q(email_proveedor__iexact=email) |

                Q(direccion_proveedor__iexact=direccion)

            ).exclude(
                ID_Proveedor=pk
            ).first()

            if proveedor_existente:

                request.session[
                    'error_duplicado_id'
                ] = proveedor_existente.ID_Proveedor

                request.session[
                    'proveedor_conflicto'
                ] = (
                    'Ya existe otro proveedor con alguno de los datos ingresados.'
                )

                return redirect(
                    'gestion_proveedores'
                )

            form.save()

            return redirect(
                'gestion_proveedores'
            )

    else:

        form = ProveedorForm(
            instance=proveedor
        )

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

    proveedor = get_object_or_404(
        Proveedores,
        ID_Proveedor=pk
    )

    if request.method == 'POST':

        proveedor.estado_proveedor = (
            not proveedor.estado_proveedor
        )

        proveedor.save()

    return redirect(
        'gestion_proveedores'
    )


# ============================================================
# TIPOS DE PRODUCTOS
# ============================================================

def gestion_tipos_productos(request):

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:
        return redirect('login')

    usuario = get_object_or_404(
        Usuarios.objects.select_related(
            'ID_Perfil'
        ),
        ID_Usuario=usuario_id
    )

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
            'busqueda': busqueda,
            'usuario': usuario
        }
    )


def crear_tipo_producto(request):

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:
        return redirect('login')

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

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:
        return redirect('login')

    tipo = get_object_or_404(
        TiposProductos,
        pk=pk
    )

    if request.method == 'POST':

        nombre = request.POST.get(
            'Nombre_tipo_producto',
            ''
        ).strip()

        if nombre:

            tipo.Nombre_tipo_producto = nombre

            tipo.save()

            messages.success(
                request,
                'Tipo de producto actualizado correctamente.'
            )

    return redirect(
        'gestion_tipos_productos'
    )


def dar_baja_tipo_producto(request, pk):

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:
        return redirect('login')

    tipo = get_object_or_404(
        TiposProductos,
        pk=pk
    )

    if request.method == 'POST':

        tipo.Estado_tipo_producto = False

        tipo.save()

        messages.success(
            request,
            'Tipo de producto dado de baja correctamente.'
        )

    return redirect(
        'gestion_tipos_productos'
    )


# ============================================================
# AGROQUÍMICOS
# ============================================================

def gestion_agroquimicos(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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
            'busqueda': busqueda,
            'usuario': usuario
        }
    )


def crear_agroquimico(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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
            'busqueda': busqueda,
            'usuario_actual': usuario
        }
    )


# ============================================================
# CREAR USUARIO
# ============================================================

def crear_usuario(request):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

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

        if len(contrasena) < 8:

            messages.error(
                request,
                'La contraseña debe tener al menos 8 caracteres.'
            )

            return redirect(
                'gestion_usuarios'
            )

        if not nombre:

            messages.error(
                request,
                'Debe ingresar el nombre del usuario.'
            )

            return redirect(
                'gestion_usuarios'
            )

        if not apellido:

            messages.error(
                request,
                'Debe ingresar el apellido del usuario.'
            )

            return redirect(
                'gestion_usuarios'
            )

        apellido_sin_tildes = ''.join(

            caracter

            for caracter in unicodedata.normalize(
                'NFD',
                apellido
            )

            if unicodedata.category(
                caracter
            ) != 'Mn'
        )

        nombre_sin_tildes = ''.join(

            caracter

            for caracter in unicodedata.normalize(
                'NFD',
                nombre
            )

            if unicodedata.category(
                caracter
            ) != 'Mn'
        )

        usuario_generado = (

            apellido_sin_tildes

            + nombre_sin_tildes[0]

        ).lower()

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

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

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
            f'ha sido modificado correctamente'
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

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:

        return redirect('panel_principal')

    usuario = get_object_or_404(
        Usuarios,
        ID_Usuario=pk
    )

    if usuario.ID_Usuario == usuario_admin.ID_Usuario:
        messages.error(
            request,
            'No puede darse de baja a sí mismo.'
        )
        return redirect(
            'gestion_usuarios'
        )

    if request.method == 'POST':

        usuario.Estado_usuario = False

        usuario.Fecha_Baja = timezone.now().date()

        usuario.save()


        messages.success(
            request,
            'Usuario dado de baja correctamente'
        )

    return redirect(
        'gestion_usuarios'
    )

# ============================================================
# ACTIVAR USUARIO
# ============================================================

def activar_usuario(request, id):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(
        Usuarios,
        ID_Usuario=id
    )

    usuario.Estado_usuario = True

    usuario.Fecha_Baja = None

    usuario.save()

    messages.success(
        request,
        f'El usuario {usuario.Usuario} fue activado correctamente'
    )

    return redirect(
        'gestion_usuarios'
    )


# ============================================================
# RESTABLECER CONTRASEÑA
# ============================================================

def restablecer_contrasena(request, pk):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(
        Usuarios,
        ID_Usuario=pk
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
                'inventario/cambiar_contrasena.html'
            )

        if len(nueva_contrasena) < 8:

            messages.error(
                request,
                'La contraseña debe tener al menos 8 caracteres.'
            )

            return render(
                request,
                'inventario/cambiar_contrasena.html'
            )

        usuario.Contrasena = make_password(
            nueva_contrasena
        )

        usuario.Cambiar_contrasena = False

        usuario.save()

        messages.success(
            request,
            'Contraseña cambiada correctamente.'
        )

        return redirect(
            'panel_principal'
        )

    return render(
        request,
        'inventario/cambiar_contrasena.html'
    )


# ============================================================
# GESTIÓN DE PERFILES
# ============================================================

def gestion_perfiles(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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
            'busqueda': busqueda,
            'usuario': usuario
        }
    )


def crear_perfil(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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

        PerfilesXPermisos.objects.filter(
            ID_Perfil=perfil
        ).delete()

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
            'Perfil actualizado correctamente.'
        )

    return redirect(
        'gestion_perfiles'
    )


def cambiar_estado_perfil(request, id):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    perfil = get_object_or_404(
        Perfiles,
        ID_Perfil=id
    )

    if request.method == 'POST':

        perfil.Estado_perfil = (
            not perfil.Estado_perfil
        )

        perfil.save(
            update_fields=[
                'Estado_perfil'
            ]
        )

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

    return redirect(
        'gestion_perfiles'
    )


# ============================================================
# GESTIÓN DE PERMISOS
# ============================================================

def gestion_permisos(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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
            'busqueda': busqueda,
            'usuario': usuario
        }
    )


def crear_permiso(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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


def editar_permiso(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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


def eliminar_permiso(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    permiso = get_object_or_404(
        Permisos,
        ID_Permiso=pk
    )

    if request.method == 'POST':

        nombre_permiso = permiso.Nombre_permiso

        PerfilesXPermisos.objects.filter(
            ID_Permiso=permiso
        ).delete()

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
# MIS PERMISOS
# ============================================================

def mis_permisos(request):

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:

        return redirect(
            'login'
        )

    usuario = get_object_or_404(
        Usuarios.objects.select_related(
            'ID_Perfil'
        ),
        ID_Usuario=usuario_id
    )

    if not usuario.ID_Perfil:
        return redirect('panel_principal')

    if usuario.ID_Perfil.Nombre_perfil != 'Vendedor':

        return redirect(
            'panel_principal'
        )

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
# TIPOS DE MOVIMIENTOS
# ============================================================

def gestion_tipos_movimientos(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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
            'busqueda': busqueda,
            'usuario': usuario
        }
    )


def crear_tipo_movimiento(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:

        return redirect(
            'login'
        )

    usuario = get_object_or_404(
        Usuarios.objects.select_related(
            'ID_Perfil'
        ),
        ID_Usuario=usuario_id
    )

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    tipo_id = request.GET.get(
        'tipo',
        ''
    ).strip()

    productos = Productos.objects.select_related(
        'ID_Tipo_producto',
        'stock'
    ).prefetch_related(
        'agroquimicos',
        'proveedores'
    ).all()

    if busqueda:

        productos = productos.filter(

            Q(Nombre_producto__icontains=busqueda) |

            Q(Descripcion_producto__icontains=busqueda)

        )

    if tipo_id:

        productos = productos.filter(
            ID_Tipo_producto_id=tipo_id
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
            'busqueda': busqueda,
            'usuario': usuario
        }
    )


def crear_producto(request):

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:

        return redirect('login')

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
            ),

            Estado_producto=request.POST.get(
                'Estado_producto',
                'Disponible'
            )

        )

        agroquimicos_ids = request.POST.getlist(
            'agroquimicos'
        )

        for agro_id in agroquimicos_ids:

            if agro_id:

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

            if proveedor_id:

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

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:

        return redirect('login')

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

        producto.Estado_producto = request.POST.get(
            'Estado_producto',
            'Disponible'
        )

        producto.save()

        ProductosXAgroquimicos.objects.filter(
            ID_Producto=producto
        ).delete()

        agroquimicos_ids = request.POST.getlist(
            'agroquimicos'
        )

        for agro_id in agroquimicos_ids:

            if agro_id:

                ProductosXAgroquimicos.objects.create(
                    ID_Producto=producto,
                    ID_Agroquimico_id=agro_id
                )

        ProductosXProveedores.objects.filter(
            ID_Producto=producto
        ).delete()

        proveedores_ids = request.POST.getlist(
            'proveedores'
        )

        for proveedor_id in proveedores_ids:

            if proveedor_id:

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


def dar_baja_producto(request, pk):

    usuario_id = request.session.get(
        'usuario_id'
    )

    if not usuario_id:

        return redirect('login')

    producto = get_object_or_404(
        Productos,
        pk=pk
    )

    if request.method == 'POST':

        producto.Estado_producto = 'No disponible'

        producto.save()

        messages.success(
            request,
            'Producto dado de baja correctamente.'
        )

    return redirect(
        'gestion_productos'
    )


# ============================================================
# PRODUCTOS POR PROVEEDOR
# ============================================================

def gestion_productos_proveedores(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    relaciones = ProductosXProveedores.objects.select_related(
        'ID_Producto',
        'ID_Proveedor'
    ).all()

    return render(
        request,
        'inventario/productos_proveedores.html',
        {
            'relaciones': relaciones,
            'usuario': usuario
        }
    )


# ============================================================
# STOCK
# ============================================================

def gestion_stock(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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
            'busqueda': busqueda,
            'usuario': usuario
        }
    )


def crear_stock(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    if request.method == 'POST':

        producto_id = request.POST.get(
            'ID_Producto'
        )

        producto = get_object_or_404(
            Productos,
            pk=producto_id
        )

        cantidad_stock = int(
            request.POST.get(
                'Cantidad_stock',
                0
            )
        )

        stock_minimo = int(
            request.POST.get(
                'Stock_minimo',
                0
            )
        )

        stock = Stock.objects.create(

            ID_Producto=producto,

            Cantidad_stock=cantidad_stock,

            Stock_minimo=stock_minimo

        )

        if cantidad_stock <= stock_minimo:

            Alertas.objects.create(

                ID_Stock=stock,

                Tipo_alerta='Stock mínimo',

                Mensaje=(

                    f'El producto {producto.Nombre_producto} '

                    f'alcanzó el stock mínimo.'

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

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    stock = get_object_or_404(
        Stock,
        pk=pk
    )

    if request.method == 'POST':

        cantidad_anterior = stock.Cantidad_stock

        stock.Cantidad_stock = int(
            request.POST.get(
                'Cantidad_stock',
                0
            )
        )

        stock.Stock_minimo = int(
            request.POST.get(
                'Stock_minimo',
                0
            )
        )

        stock.save()

        if (

            cantidad_anterior > stock.Stock_minimo

            and

            stock.Cantidad_stock <= stock.Stock_minimo

        ):

            Alertas.objects.create(

                ID_Stock=stock,

                Tipo_alerta='Stock mínimo',

                Mensaje=(

                    f'El producto '

                    f'{stock.ID_Producto.Nombre_producto} '

                    f'alcanzó el stock mínimo.'

                )

            )

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

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

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
            'stock': stock,
            'usuario': usuario
        }
    )


def crear_movimiento_stock(request):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

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

        if cantidad <= 0:

            messages.error(
                request,
                'La cantidad debe ser mayor a cero.'
            )

            return redirect(
                'gestion_movimientos_stock'
            )

        cantidad_anterior = stock.Cantidad_stock

        nombre_movimiento = (
            tipo_movimiento.Nombre_tipo_movimiento.lower()
        )

        if nombre_movimiento == 'salida por venta':

            if cantidad > stock.Cantidad_stock:

                messages.error(
                    request,
                    'No hay suficiente stock disponible.'
                )

                return redirect(
                    'gestion_movimientos_stock'
                )

            stock.Cantidad_stock -= cantidad

        elif nombre_movimiento == 'salida por vencimiento':

            if cantidad > stock.Cantidad_stock:

                messages.error(
                    request,
                    'No hay suficiente stock disponible.'
                )

                return redirect(
                    'gestion_movimientos_stock'
                )

            stock.Cantidad_stock -= cantidad

        else:

            messages.error(
                request,
                'El tipo de movimiento no es válido.'
            )

            return redirect(
                'gestion_movimientos_stock'
            )

        stock.save()

        MovimientosStock.objects.create(

            ID_Usuario=usuario,

            ID_Tipo_movimiento=tipo_movimiento,

            ID_Stock=stock,

            Cantidad=cantidad

        )

        if (

            cantidad_anterior > stock.Stock_minimo

            and

            stock.Cantidad_stock <= stock.Stock_minimo

        ):

            Alertas.objects.create(

                ID_Stock=stock,

                Tipo_alerta='Stock mínimo',

                Mensaje=(

                    f'El producto '

                    f'{stock.ID_Producto.Nombre_producto} '

                    f'alcanzó el stock mínimo.'

                )

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

def generar_alertas_vencimiento():

    fecha_actual = timezone.localdate()

    fecha_limite = fecha_actual + timedelta(
        days=30
    )

    productos = Productos.objects.filter(

        Fecha_vencimiento__isnull=False,

        Fecha_vencimiento__gte=fecha_actual,

        Fecha_vencimiento__lte=fecha_limite

    )

    for producto in productos:

        try:

            stock = Stock.objects.get(
                ID_Producto=producto
            )

        except Stock.DoesNotExist:

            continue

        existe_alerta = Alertas.objects.filter(

            ID_Stock=stock,

            Tipo_alerta='Vencimiento',

            Mensaje__icontains=producto.Nombre_producto

        ).exists()

        if not existe_alerta:

            dias_restantes = (

                producto.Fecha_vencimiento

                - fecha_actual

            ).days

            Alertas.objects.create(

                ID_Stock=stock,

                Tipo_alerta='Vencimiento',

                Mensaje=(

                    f'El producto {producto.Nombre_producto} '

                    f'vence en {dias_restantes} días '

                    f'({producto.Fecha_vencimiento.strftime("%d/%m/%Y")}).'

                )

            )


def gestion_alertas(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    generar_alertas_vencimiento()

    fecha = request.GET.get(
        'fecha',
        ''
    ).strip()

    fecha_desde = request.GET.get(
        'fecha_desde',
        ''
    ).strip()

    fecha_hasta = request.GET.get(
        'fecha_hasta',
        ''
    ).strip()

    usuario_id = request.GET.get(
        'usuario',
        ''
    ).strip()

    tipo_alerta = request.GET.get(
        'tipo',
        ''
    ).strip()

    producto_id = request.GET.get(
        'producto',
        ''
    ).strip()

    stock_id = request.GET.get(
        'stock',
        ''
    ).strip()

    alertas = Alertas.objects.select_related(

        'ID_Stock',

        'ID_Stock__ID_Producto'

    ).all().order_by(

        '-Fecha_hora_historial_alerta'

    )

    if fecha:

        alertas = alertas.filter(

            Fecha_hora_historial_alerta__date=fecha

        )

    if fecha_desde:

        alertas = alertas.filter(

            Fecha_hora_historial_alerta__date__gte=fecha_desde

        )

    if fecha_hasta:

        alertas = alertas.filter(

            Fecha_hora_historial_alerta__date__lte=fecha_hasta

        )

    if usuario_id:

        stock_ids = MovimientosStock.objects.filter(

            ID_Usuario_id=usuario_id

        ).values(
            'ID_Stock'
        )

        alertas = alertas.filter(
            ID_Stock__in=stock_ids
        )

    if tipo_alerta:

        alertas = alertas.filter(
            Tipo_alerta=tipo_alerta
        )

    if producto_id:

        alertas = alertas.filter(
            ID_Stock__ID_Producto_id=producto_id
        )

    if stock_id:

        alertas = alertas.filter(
            ID_Stock_id=stock_id
        )

    usuarios = Usuarios.objects.filter(

        Estado_usuario=True

    ).order_by(

        'Apellido_usuario',

        'Nombre_usuario'

    )

    productos = Productos.objects.all().order_by(
        'Nombre_producto'
    )

    stock = Stock.objects.select_related(
        'ID_Producto'
    ).all().order_by(
        'ID_Producto__Nombre_producto'
    )

    for alerta in alertas:

        alerta.usuarios_relacionados = Usuarios.objects.filter(

            ID_Usuario__in=MovimientosStock.objects.filter(

                ID_Stock=alerta.ID_Stock

            ).values(
                'ID_Usuario'
            )

        ).distinct()

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