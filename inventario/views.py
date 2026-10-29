from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
import unicodedata

from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.http import JsonResponse
from django.contrib.staticfiles import finders
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Count, Prefetch, ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from .auditoria import snapshot, registrar_auditoria
from .forms import ProveedorForm
from .permissions import usuario_con_acceso

from .models import (
    TiposProductos,
    Subtipos,
    Proveedores,
    Remitos,
    TiposMovimientos,
    Perfiles,
    Permisos,
    PerfilesXPermisos,
    Usuarios,
    Productos,
    Lotes,
    Stock,
    Alertas,
    MovimientosStock,
    LogAuditoria,
)


# ============================================================
# CONTROL DE ACCESO
# ============================================================

PERFILES_ADMIN = ('Administrador',)


def usuario_autenticado(request):
    """Devuelve el usuario logueado si está activo y tiene perfil activo."""

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
    """Verifica que el usuario tenga un perfil administrativo."""

    usuario = usuario_autenticado(request)

    if not usuario:
        return None

    if usuario.ID_Perfil.Nombre_perfil not in PERFILES_ADMIN:
        return None

    return usuario

def usuario_es_vendedor(request):
    """Verifica que el usuario tenga el perfil Vendedor."""

    usuario = usuario_autenticado(request)

    if not usuario:
        return None

    if usuario.ID_Perfil.Nombre_perfil != 'Vendedor':
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

            elif check_password(
                password_input,
                usuario.Contrasena
            ):

                request.session['usuario_id'] = usuario.ID_Usuario
                request.session['usuario_nombre'] = usuario.Usuario
                request.session['perfil_id'] = usuario.ID_Perfil.ID_Perfil
                request.session['perfil_nombre'] = (
                    usuario.ID_Perfil.Nombre_perfil
                )

                registrar_auditoria(
                    usuario=usuario,
                    entidad="USUARIOS",
                    objeto=usuario,
                    accion="INICIO_SESION",
                    antes={},
                    despues={"accion": "Inicio de sesión"}
                )

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

    usuario = usuario_autenticado(request)

    if usuario:
        registrar_auditoria(
            usuario=usuario,
            entidad="USUARIOS",
            objeto=usuario,
            accion="CIERRE_SESION",
            antes={},
            despues={"accion": "Cierre de sesión"}
        )

    request.session.flush()

    return redirect('login')


# ============================================================
# PANEL PRINCIPAL
# ============================================================

def panel_principal(request):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    alertas_vencimiento = generar_alertas_vencimiento()

    return render(
        request,
        'inventario/panel_principal.html',
        {
            'usuario': usuario,
            'alertas_vencimiento': alertas_vencimiento
        }
    )


# ============================================================
# PROVEEDORES
# ============================================================

def _proveedor_duplicado(form, excluir_pk=None):
    """Busca otro proveedor que coincida en nombre, teléfono, email o dirección."""

    nombre = form.cleaned_data['nombre_proveedor'].strip()
    telefono = (
        form.cleaned_data.get('telefono_proveedor') or ''
    ).strip()
    email = (
        form.cleaned_data.get('email_proveedor') or ''
    ).strip()
    direccion = (
        form.cleaned_data.get('direccion_proveedor') or ''
    ).strip()

    filtros = Q(nombre_proveedor__iexact=nombre)

    if telefono:
        filtros |= Q(telefono_proveedor=telefono)

    if email:
        filtros |= Q(email_proveedor__iexact=email)

    if direccion:
        filtros |= Q(direccion_proveedor__iexact=direccion)

    proveedores = Proveedores.objects.filter(filtros)

    if excluir_pk is not None:
        proveedores = proveedores.exclude(
            ID_Proveedor=excluir_pk
        )

    return proveedores.first()



def gestion_proveedores(request):

    usuario = usuario_con_acceso(request, 'proveedores')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para consultar proveedores.'
        )
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

    usuario = usuario_con_acceso(request, 'proveedores')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para crear proveedores.'
        )
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_proveedores')

    form = ProveedorForm(request.POST)

    if not form.is_valid():

        for campo, errores in form.errors.items():

            if campo in form.fields:
                etiqueta = form.fields[campo].label or campo
            else:
                etiqueta = 'Datos del proveedor'

            for error in errores:
                messages.error(
                    request,
                    f'{etiqueta}: {error}'
                )

        return redirect('gestion_proveedores')

    existente = _proveedor_duplicado(form)

    if existente:

        request.session['error_duplicado_id'] = (
            existente.ID_Proveedor
        )

        request.session['proveedor_conflicto'] = (
            'Ya existe un proveedor con alguno '
            'de los datos ingresados.'
        )

        return redirect('gestion_proveedores')

    form.save()

    messages.success(
        request,
        'Proveedor registrado correctamente.'
    )

    return redirect('gestion_proveedores')


def editar_proveedor(request, pk):

    usuario = usuario_con_acceso(request, 'proveedores')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para editar proveedores.'
        )
        return redirect('panel_principal')

    proveedor = get_object_or_404(
        Proveedores,
        ID_Proveedor=pk
    )

    antes = snapshot(proveedor)         # <-- NUEVO: antes del formulario

    estado_original = proveedor.estado_proveedor

    if request.method != 'POST':
        return redirect('gestion_proveedores')

    form = ProveedorForm(
        request.POST,
        instance=proveedor
    )

    if not form.is_valid():

        for campo, errores in form.errors.items():

            if campo in form.fields:
                etiqueta = form.fields[campo].label or campo
            else:
                etiqueta = 'Datos del proveedor'

            for error in errores:
                messages.error(
                    request,
                    f'{etiqueta}: {error}'
                )

        return redirect('gestion_proveedores')

    existente = _proveedor_duplicado(
        form,
        excluir_pk=pk
    )

    if existente:

        request.session['error_duplicado_id'] = (
            existente.ID_Proveedor
        )

        request.session['proveedor_conflicto'] = (
            'Ya existe otro proveedor con alguno '
            'de los datos ingresados.'
        )

        return redirect('gestion_proveedores')

    proveedor_actualizado = form.save(commit=False)
    proveedor_actualizado.estado_proveedor = estado_original
    proveedor_actualizado.save()

    registrar_auditoria(
        usuario,
        'Proveedores',
        proveedor_actualizado,
        'MODIFICACION',
        antes,
        snapshot(proveedor_actualizado)
    )

    messages.success(
        request,
        'Proveedor actualizado correctamente.'
    )

    return redirect('gestion_proveedores')


def cambiar_estado_proveedor(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    proveedor = get_object_or_404(
        Proveedores,
        ID_Proveedor=pk
    )

    if request.method != 'POST':
        return redirect('gestion_proveedores')

    estado_solicitado = request.POST.get(
        'estado',
        ''
    ).strip().lower()

    antes = snapshot(proveedor)

    if estado_solicitado == 'inactivo':

        proveedor.estado_proveedor = False

        mensaje = (
            f'El proveedor "{proveedor.nombre_proveedor}" '
            'fue dado de baja correctamente.'
        )

    elif estado_solicitado == 'activo':

        proveedor.estado_proveedor = True

        mensaje = (
            f'El proveedor "{proveedor.nombre_proveedor}" '
            'fue activado correctamente.'
        )

    else:
        messages.error(
            request,
            'El estado solicitado no es válido.'
        )

        return redirect('gestion_proveedores')

    proveedor.save(
        update_fields=['estado_proveedor']
    )

    registrar_auditoria(usuario, 'Proveedores', proveedor, 'MODIFICACION', antes, snapshot(proveedor))

    messages.success(request, mensaje)

    return redirect('gestion_proveedores')

# ============================================================
# TIPOS DE PRODUCTOS
# ============================================================

def gestion_tipos_productos(request):

    usuario = usuario_con_acceso(request, 'tipos')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para consultar tipos de productos.'
        )
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()

    tipos = TiposProductos.objects.annotate(
        cantidad_productos=Count('productos', distinct=True),
        cantidad_subtipos=Count('subtipos', distinct=True),
    )

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
            'usuario': usuario,
            'total_tipos': TiposProductos.objects.count(),
            'total_subtipos': Subtipos.objects.count(),
        }
    )

# ============================================================
# CREAR TIPO DE PRODUCTO
# ============================================================

def crear_tipo_producto(request):

    usuario = usuario_con_acceso(
        request,
        'tipos',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para gestionar tipos de productos.'
        )
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_tipos_productos')

    nombre = request.POST.get(
        'Nombre_tipo_producto',
        ''
    ).strip()

    if not nombre:
        messages.error(
            request,
            'Debe ingresar el nombre del tipo de producto.'
        )
        return redirect('gestion_tipos_productos')

    existe = TiposProductos.objects.filter(
        Nombre_tipo_producto__iexact=nombre
    ).exists()

    if existe:
        messages.error(
            request,
            'Ya existe un tipo de producto con ese nombre.'
        )
        return redirect('gestion_tipos_productos')

    TiposProductos.objects.create(
        Nombre_tipo_producto=nombre,
        Estado_tipo_producto=True
    )

    messages.success(
        request,
        'Tipo de producto registrado correctamente.'
    )

    return redirect('gestion_tipos_productos')


# ============================================================
# EDITAR TIPO DE PRODUCTO
# ============================================================

def editar_tipo_producto(request, pk):

    usuario = usuario_con_acceso(
        request,
        'tipos',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para gestionar tipos de productos.'
        )
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_tipos_productos')

    tipo = get_object_or_404(
        TiposProductos,
        ID_Tipo_producto=pk
    )

    antes = snapshot(tipo)   

    nombre = request.POST.get(
        'Nombre_tipo_producto',
        ''
    ).strip()

    estado_recibido = request.POST.get(
        'Estado_tipo_producto',
        ''
    )

    if not nombre:
        messages.error(
            request,
            'Debe ingresar el nombre del tipo de producto.'
        )
        return redirect('gestion_tipos_productos')

    if estado_recibido not in ('True', 'False'):
        messages.error(
            request,
            'El estado seleccionado no es válido.'
        )
        return redirect('gestion_tipos_productos')

    existe = TiposProductos.objects.filter(
        Nombre_tipo_producto__iexact=nombre
    ).exclude(
        ID_Tipo_producto=pk
    ).exists()

    if existe:
        messages.error(
            request,
            'Ya existe otro tipo de producto con ese nombre.'
        )
        return redirect('gestion_tipos_productos')

    tipo.Nombre_tipo_producto = nombre
    tipo.Estado_tipo_producto = (estado_recibido == 'True')
    tipo.save(
        update_fields=[
            'Nombre_tipo_producto',
            'Estado_tipo_producto',
        ]
    )

    registrar_auditoria(                # <-- NUEVO
        usuario,
        'Tipos de productos',
        tipo,
        'MODIFICACION',
        antes,
        snapshot(tipo)
    )

    messages.success(
        request,
        f'Tipo de producto actualizado correctamente. '
        f'Estado: {"Activo" if tipo.Estado_tipo_producto else "Inactivo"}.'
    )

    return redirect('gestion_tipos_productos')


# ============================================================
# ELIMINAR TIPO DE PRODUCTO
# No permite eliminar si tiene productos o subtipos asociados.
# ============================================================

def eliminar_tipo_producto(request, pk):

    usuario = usuario_con_acceso(
        request,
        'tipos',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para gestionar tipos de productos.'
        )
        return redirect('panel_principal')

    if not usuario_es_administrador(request):
        messages.error(
            request,
            'No tenés permiso para eliminar tipos de productos.'
        )
        return redirect('gestion_tipos_productos')

    if request.method != 'POST':
        return redirect('gestion_tipos_productos')

    try:
        with transaction.atomic():

            tipo = get_object_or_404(
                TiposProductos.objects.select_for_update(),
                ID_Tipo_producto=pk
            )

            nombre = tipo.Nombre_tipo_producto

            # Contar los productos asociados al tipo.
            cantidad_productos = Productos.objects.filter(
                ID_Tipo_producto=tipo
            ).count()

            # Contar los subtipos asociados al tipo.
            cantidad_subtipos = Subtipos.objects.filter(
                ID_Tipo_producto=tipo
            ).count()

            if cantidad_productos > 0:
                messages.error(
                    request,
                    f'No se puede eliminar el tipo "{nombre}" porque '
                    f'tiene {cantidad_productos} producto(s) asociado(s).'
                )
                return redirect('gestion_tipos_productos')

            if cantidad_subtipos > 0:
                messages.error(
                    request,
                    f'No se puede eliminar el tipo "{nombre}" porque '
                    f'tiene {cantidad_subtipos} subtipo(s) asociado(s).'
                )
                return redirect('gestion_tipos_productos')

            tipo.delete()

        messages.success(
            request,
            f'El tipo "{nombre}" fue eliminado correctamente.'
        )

    except ProtectedError:
        messages.error(
            request,
            f'No se puede eliminar el tipo "{nombre}" porque '
            'tiene otros registros relacionados.'
        )

    return redirect('gestion_tipos_productos')




# ============================================================
# SUBTIPOS
# ============================================================

def _subtipo_tiene_descripcion():
    """Comprueba si Subtipos tiene el campo Descripcion_subtipo."""

    return any(
        campo.name == 'Descripcion_subtipo'
        for campo in Subtipos._meta.get_fields()
    )


def gestion_subtipos(request):
    usuario = usuario_con_acceso(request, 'subtipos')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para consultar subtipos.'
        )
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()

    subtipos = Subtipos.objects.select_related(
        'ID_Tipo_producto'
    ).order_by(
        'Nombre_subtipo'
    )

    if busqueda:
        subtipos = subtipos.filter(
            Nombre_subtipo__icontains=busqueda
        )

    tipos_productos = TiposProductos.objects.order_by(
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

        nombre = request.POST.get(
            'Nombre_subtipo',
            ''
        ).strip()

        tipo_id = request.POST.get('ID_Tipo_producto')

        if not nombre:
            messages.error(
                request,
                'Debe ingresar el nombre del subtipo.'
            )

            return redirect('gestion_subtipos')

        if not tipo_id:
            messages.error(
                request,
                'Debe seleccionar un tipo de producto.'
            )

            return redirect('gestion_subtipos')

        tipo = get_object_or_404(
            TiposProductos,
            ID_Tipo_producto=tipo_id,
        )

        # No permitir asociar subtipos a tipos inactivos
        if not tipo.Estado_tipo_producto:
            messages.error(
                request,
                'No se pueden asociar subtipos a un tipo de producto inactivo.'
        )
            return redirect('gestion_subtipos')

        existe = Subtipos.objects.filter(
            ID_Tipo_producto=tipo,
            Nombre_subtipo__iexact=nombre

        ).exists()

        if existe:
            messages.error(
                request,
                'Ya existe un subtipo con ese nombre '
                'para el tipo seleccionado.'
            )

            return redirect('gestion_subtipos')

        datos_subtipo = {
            'ID_Tipo_producto': tipo,
            'Nombre_subtipo': nombre,
        }

        if _subtipo_tiene_descripcion():
            datos_subtipo['Descripcion_subtipo'] = (
                request.POST.get(
                    'Descripcion_subtipo',
                    ''
                ).strip() or None
            )

        Subtipos.objects.create(**datos_subtipo)

        messages.success(
            request,
            'Subtipo creado correctamente.'
        )

    return redirect('gestion_subtipos')


def editar_subtipo(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    subtipo = get_object_or_404(
        Subtipos,
        ID_Subtipo=pk
    )

    antes = snapshot(subtipo)  

    if request.method == 'POST':

        nombre = request.POST.get(
            'Nombre_subtipo',
            ''
        ).strip()

        tipo_id = request.POST.get('ID_Tipo_producto')

        if not nombre:
            messages.error(
                request,
                'Debe ingresar el nombre del subtipo.'
            )

            return redirect('gestion_subtipos')

        if not tipo_id:
            messages.error(
                request,
                'Debe seleccionar un tipo de producto.'
            )

            return redirect('gestion_subtipos')

        tipo = get_object_or_404(
            TiposProductos,
            ID_Tipo_producto=tipo_id,
        )

        # No permitir asociar subtipos a tipos inactivos
        if not tipo.Estado_tipo_producto:
            messages.error(
                request,
                'No se pueden asociar subtipos a un tipo de producto inactivo.'
            )
            return redirect('gestion_subtipos')


        if (
            tipo.pk != subtipo.ID_Tipo_producto_id
            and Productos.objects.filter(ID_Subtipo=subtipo).exists()
        ):
            messages.error(
                request,
                'No se puede cambiar el tipo de un subtipo que tiene '
                'productos asociados.'
            )

            return redirect('gestion_subtipos')

        existe = Subtipos.objects.filter(
            ID_Tipo_producto=tipo,
            Nombre_subtipo__iexact=nombre
        ).exclude(
            ID_Subtipo=pk
        ).exists()

        if existe:
            messages.error(
                request,
                'Ya existe un subtipo con ese nombre '
                'para el tipo seleccionado.'
            )

            return redirect('gestion_subtipos')

        subtipo.ID_Tipo_producto = tipo
        subtipo.Nombre_subtipo = nombre

        if _subtipo_tiene_descripcion():
            subtipo.Descripcion_subtipo = (
                request.POST.get(
                    'Descripcion_subtipo',
                    ''
                ).strip() or None
            )

        subtipo.save()

        registrar_auditoria(            # <-- NUEVO
            usuario,
            'Subtipos',
            subtipo,
            'MODIFICACION',
            antes,
            snapshot(subtipo)
        )

        messages.success(
            request,
            'Subtipo modificado correctamente.'
        )

    return redirect('gestion_subtipos')


def eliminar_subtipo(request, pk):
    """Elimina un subtipo solo si no tiene productos asociados."""

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_subtipos')

    subtipo = get_object_or_404(
        Subtipos,
        ID_Subtipo=pk
    )

    nombre = subtipo.Nombre_subtipo

    if Productos.objects.filter(ID_Subtipo=subtipo).exists():
        messages.error(
            request,
            f'No se puede eliminar el subtipo "{nombre}": tiene '
            'productos asociados.'
        )
        return redirect('gestion_subtipos')

    try:
        with transaction.atomic():
            subtipo.delete()
    except ProtectedError:
        messages.error(
            request,
            f'No se puede eliminar el subtipo "{nombre}": tiene '
            'registros asociados.'
        )
        return redirect('gestion_subtipos')

    messages.success(
        request,
        f'El subtipo "{nombre}" fue eliminado.'
    )

    return redirect('gestion_subtipos')


# ============================================================
# GESTIÓN DE USUARIOS
# ============================================================

def gestion_usuarios(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()

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
            messages.error(
                request,
                'Debe seleccionar un perfil.'
            )

            return redirect('gestion_usuarios')

        perfil = get_object_or_404(
            Perfiles,
            ID_Perfil=perfil_id
        )

        if not perfil.Estado_perfil:
            messages.error(
                request,
                'No se pueden registrar usuarios con un perfil inactivo.'
            )
            return redirect('gestion_usuarios')

        dni = request.POST.get('DNI', '').strip()
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

        if not dni or not dni.isdigit():
            messages.error(
                request,
                'Debe ingresar un DNI válido.'
            )

            return redirect('gestion_usuarios')

        if not nombre:
            messages.error(
                request,
                'Debe ingresar el nombre del usuario.'
            )

            return redirect('gestion_usuarios')

        if not apellido:
            messages.error(
                request,
                'Debe ingresar el apellido del usuario.'
            )

            return redirect('gestion_usuarios')

        if not email:
            messages.error(
                request,
                'Debe ingresar el correo electrónico.'
            )

            return redirect('gestion_usuarios')

        if len(contrasena) < 8:
            messages.error(
                request,
                'La contraseña debe tener al menos 8 caracteres.'
            )

            return redirect('gestion_usuarios')

        if Usuarios.objects.filter(DNI=int(dni)).exists():
            messages.error(
                request,
                'Ya existe un usuario con ese DNI.'
            )

            return redirect('gestion_usuarios')

        if Usuarios.objects.filter(
            Email_usuario__iexact=email
        ).exists():
            messages.error(
                request,
                'Ya existe un usuario con ese correo electrónico.'
            )

            return redirect('gestion_usuarios')

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
            apellido_sin_tildes + nombre_sin_tildes[0]
        ).lower()

        if Usuarios.objects.filter(
            Usuario=usuario_generado
        ).exists():
            messages.error(
                request,
                f'El usuario {usuario_generado} ya existe.'
            )

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
            'ha sido registrado correctamente. '
            'Deberá cambiar su contraseña '
            'en el próximo inicio de sesión.'
        )

    return redirect('gestion_usuarios')


def editar_usuario(request, pk):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(
        Usuarios,
        ID_Usuario=pk
    )

    antes = snapshot(usuario)

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
                {'usuario': usuario}
            )

        email_existente = Usuarios.objects.filter(
            Email_usuario__iexact=nuevo_email
        ).exclude(
            ID_Usuario=pk
        ).exists()

        if email_existente:
            messages.error(
                request,
                'Ya existe otro usuario con ese correo electrónico.'
            )

            return render(
                request,
                'inventario/editar_usuario.html',
                {'usuario': usuario}
            )

        usuario.Email_usuario = nuevo_email
        usuario.save()

        registrar_auditoria(usuario_admin, 'Usuarios', usuario, 'MODIFICACION', antes, snapshot(usuario))

        messages.success(
            request,
            f'El usuario {usuario.Usuario} '
            'ha sido modificado correctamente.'
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

    usuario = get_object_or_404(
        Usuarios,
        ID_Usuario=pk
    )

    if usuario.ID_Usuario == usuario_admin.ID_Usuario:
        messages.error(
            request,
            'No puede darse de baja a sí mismo.'
        )

        return redirect('gestion_usuarios')

    if request.method == 'POST':

        antes = snapshot(usuario)

        usuario.Estado_usuario = False
        usuario.Fecha_Baja = timezone.now().date()
        usuario.save()

        registrar_auditoria(usuario_admin, 'Usuarios', usuario, 'MODIFICACION', antes, snapshot(usuario))

        messages.success(
            request,
            'Usuario dado de baja correctamente.'
        )

    return redirect('gestion_usuarios')


def activar_usuario(request, id):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(
        Usuarios,
        ID_Usuario=id
    )

    if request.method == 'POST':
        # Verificar que el perfil del usuario esté activo.
        if not usuario.ID_Perfil.Estado_perfil:
            messages.error(
                request,
                'No se puede activar el usuario porque su perfil está inactivo.'
            )
            return redirect('gestion_usuarios')

        antes = snapshot(usuario)

        usuario.Estado_usuario = True
        usuario.Fecha_Baja = None
        usuario.save()

        registrar_auditoria(usuario_admin, 'Usuarios', usuario, 'MODIFICACION', antes, snapshot(usuario))

        messages.success(
            request,
            f'El usuario {usuario.Usuario} '
            'fue activado correctamente.'
        )

    return redirect('gestion_usuarios')


def restablecer_contrasena(request, pk):

    usuario_admin = usuario_es_administrador(request)

    if not usuario_admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(
        Usuarios,
        ID_Usuario=pk
    )

    if request.method != 'POST':
        return redirect('gestion_usuarios')

    nueva_contrasena = request.POST.get('nueva_contrasena', '')
    confirmar_contrasena = request.POST.get('confirmar_contrasena', '')


    if nueva_contrasena != confirmar_contrasena:
        messages.error(request, 'Las contraseñas no coinciden.')
        return redirect('gestion_usuarios')
    
    if len(nueva_contrasena) < 8:
        messages.error(
            request,
            'La contraseña debe tener al menos 8 caracteres.'
        )
        return redirect('gestion_usuarios')

    antes = snapshot(usuario)
    antes['Contrasena'] = 'anterior'

    usuario.Contrasena = make_password(nueva_contrasena)
    usuario.Cambiar_contrasena = True
    usuario.save()

    despues = snapshot(usuario)
    despues['Contrasena'] = 'restablecida'
    registrar_auditoria(usuario_admin, 'Usuarios', usuario, 'MODIFICACION', antes, despues)

    messages.success(
        request,
        f'La contraseña del usuario {usuario.Usuario} '
        'fue restablecida correctamente. '
        'Deberá cambiarla en el próximo inicio de sesión.'
    )

    return redirect('gestion_usuarios')



def cambiar_contrasena(request):
    usuario = usuario_autenticado(request)

    if not usuario:
        request.session.flush()
        return redirect('login')

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
                'inventario/cambiar_contrasena.html',
                {'usuario': usuario}
            )

        if len(nueva_contrasena) < 8:
            messages.error(
                request,
                'La contraseña debe tener al menos 8 caracteres.'
            )

            return render(
                request,
                'inventario/cambiar_contrasena.html',
                {'usuario': usuario}
            )

        usuario.Contrasena = make_password(nueva_contrasena)
        usuario.Cambiar_contrasena = False
        usuario.save()

        messages.success(
            request,
            'Contraseña cambiada correctamente.'
        )

        return redirect('panel_principal')

    return render(
        request,
        'inventario/cambiar_contrasena.html',
        {'usuario': usuario}
    )


# ============================================================
# GESTIÓN DE PERFILES
# ============================================================

def _snapshot_perfil(perfil):
    datos = snapshot(perfil)
    datos['permisos'] = ', '.join(sorted(
        PerfilesXPermisos.objects
        .filter(ID_Perfil=perfil)
        .values_list('ID_Permiso__Nombre_permiso', flat=True)
    ))
    return datos

def gestion_perfiles(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()

    perfiles = Perfiles.objects.prefetch_related(
        'permisos'
    ).annotate(
        usuarios_activos=Count(
            'usuarios',
            filter=Q(usuarios__Estado_usuario=True),
            distinct=True
        )
    ).order_by('ID_Perfil')

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
            'usuario': usuario,
            'perfiles_admin': PERFILES_ADMIN,
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

            return redirect('gestion_perfiles')

        if Perfiles.objects.filter(
            Nombre_perfil__iexact=nombre_perfil
        ).exists():
            messages.error(
                request,
                'Ya existe un perfil con ese nombre.'
            )

            return redirect('gestion_perfiles')

        permisos_ids = request.POST.getlist('permisos')

        with transaction.atomic():

            perfil = Perfiles.objects.create(
                Nombre_perfil=nombre_perfil
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

    return redirect('gestion_perfiles')


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

            return redirect('gestion_perfiles')

        existe = Perfiles.objects.filter(
            Nombre_perfil__iexact=nombre_perfil
        ).exclude(
            ID_Perfil=pk
        ).exists()

        if existe:
            messages.error(
                request,
                'Ya existe otro perfil con ese nombre.'
            )

            return redirect('gestion_perfiles')

        permisos_ids = request.POST.getlist('permisos')

        antes = _snapshot_perfil(perfil)

        with transaction.atomic():

            perfil.Nombre_perfil = nombre_perfil
            perfil.save()

            PerfilesXPermisos.objects.filter(
                ID_Perfil=perfil
            ).delete()

            for permiso_id in permisos_ids:

                permiso = get_object_or_404(
                    Permisos,
                    ID_Permiso=permiso_id
                )

                PerfilesXPermisos.objects.create(
                    ID_Perfil=perfil,
                    ID_Permiso=permiso
                )

            registrar_auditoria(usuario, 'Perfiles', perfil, 'MODIFICACION', antes, _snapshot_perfil(perfil))

        messages.success(
            request,
            'Perfil actualizado correctamente.'
        )

    return redirect('gestion_perfiles')


# ============================================================
# CAMBIAR ESTADO DEL PERFIL
# ============================================================

def cambiar_estado_perfil(request, id):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_perfiles')

    perfil = get_object_or_404(
        Perfiles,
        ID_Perfil=id
    )

    # No permitir dar de baja perfiles de sistema.
    if (
        perfil.Estado_perfil
        and perfil.Nombre_perfil in PERFILES_ADMIN
    ):
        messages.error(
            request,
            'No se puede dar de baja un perfil de sistema.'
        )
        return redirect('gestion_perfiles')

    # No permitir dar de baja el perfil del usuario actual.
    if (
        perfil.ID_Perfil == usuario.ID_Perfil.ID_Perfil
        and perfil.Estado_perfil
    ):
        messages.error(
            request,
            'No puede dar de baja el perfil con el que inició sesión.'
        )
        return redirect('gestion_perfiles')

    antes = snapshot(perfil)

    # Si está activo, se intenta dar de baja.
    if perfil.Estado_perfil:

        usuarios_asociados = Usuarios.objects.filter(
            ID_Perfil=perfil
        ).exists()

        if usuarios_asociados:
            messages.error(
                request,
                'No se puede dar de baja el perfil porque tiene '
                'usuarios asociados. Primero debe asignarles '
                'otro perfil.'
            )
            return redirect('gestion_perfiles')

        perfil.Estado_perfil = False
        perfil.save(update_fields=['Estado_perfil'])

        registrar_auditoria(usuario, 'Perfiles', perfil, 'MODIFICACION', antes, snapshot(perfil))

        messages.success(
            request,
            f'El perfil "{perfil.Nombre_perfil}" '
            'fue dado de baja correctamente.'
        )

    else:
        # Si está inactivo, se intenta activar.
        perfil.Estado_perfil = True
        perfil.save(update_fields=['Estado_perfil'])

        registrar_auditoria(usuario, 'Perfiles', perfil, 'MODIFICACION', antes, snapshot(perfil))

        messages.success(
            request,
            f'El perfil "{perfil.Nombre_perfil}" '
            'fue activado correctamente.'
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

            return redirect('gestion_permisos')

        if Permisos.objects.filter(
            Nombre_permiso__iexact=nombre_permiso
        ).exists():
            messages.error(
                request,
                'Ya existe un permiso con ese nombre.'
            )

            return redirect('gestion_permisos')

        Permisos.objects.create(
            Nombre_permiso=nombre_permiso,
            Descripcion_permiso=descripcion_permiso
        )

        messages.success(
            request,
            'Permiso creado correctamente.'
        )

    return redirect('gestion_permisos')


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

            return redirect('gestion_permisos')

        existe = Permisos.objects.filter(
            Nombre_permiso__iexact=nombre_permiso
        ).exclude(
            ID_Permiso=pk
        ).exists()

        if existe:
            messages.error(
                request,
                'Ya existe otro permiso con ese nombre.'
            )

            return redirect('gestion_permisos')

        antes = snapshot(permiso)

        permiso.Nombre_permiso = nombre_permiso
        permiso.Descripcion_permiso = descripcion_permiso
        permiso.save()

        registrar_auditoria(usuario, 'Permisos', permiso, 'MODIFICACION', antes, snapshot(permiso))

        messages.success(
            request,
            'Permiso modificado correctamente.'
        )

    return redirect('gestion_permisos')


@require_POST
def eliminar_permiso(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    permiso = get_object_or_404(
        Permisos,
        ID_Permiso=pk
    )

    nombre_permiso = permiso.Nombre_permiso

    perfiles_asignados = list(
        permiso.perfiles.values_list('Nombre_perfil', flat=True)
    )

    if perfiles_asignados:
        messages.error(
            request,
            f'No se puede eliminar el permiso "{nombre_permiso}": '
            f'está asignado a {", ".join(perfiles_asignados)}. '
            'Quítelo primero desde Editar perfil.'
        )
        return redirect('gestion_permisos')

    permiso.delete()

    messages.success(
        request,
        f'El permiso "{nombre_permiso}" fue eliminado correctamente.'
    )

    return redirect('gestion_permisos')



# ============================================================
# MIS PERMISOS
# ============================================================

def mis_permisos(request):
    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    # Solo permite acceder al perfil de Vendedor.
    if usuario.ID_Perfil.Nombre_perfil != 'Vendedor':
        return redirect('panel_principal')

    # Obtiene los permisos asignados al perfil del usuario.
    permisos = usuario.ID_Perfil.permisos.all()

    return render(
        request,
        'inventario/mis_permisos.html',
        {
            'usuario': usuario,
            'permisos': permisos,
            'activo': 'mis_permisos',
        }
    )


# ============================================================
# PRODUCTOS
# ============================================================

def _leer_datos_producto(request, estado_por_defecto):
    """Lee y valida los datos del producto y su subtipo."""

    tipo_id = request.POST.get(
        'ID_Tipo_producto', ''
    ).strip()

    subtipo_id = request.POST.get(
        'ID_Subtipo', ''
    ).strip()

    marca = request.POST.get('Marca', '').strip()
    nombre = request.POST.get('Nombre_producto', '').strip()
    descripcion = request.POST.get(
        'Descripcion_producto', ''
    ).strip()

    precio_input = request.POST.get('Precio', '').strip()
    cantidad_input = request.POST.get(
        'Cantidad_presentacion', ''
    ).strip()

    unidad_medida = request.POST.get(
        'Unidad_medida_producto', ''
    ).strip()

    estado_producto = request.POST.get(
        'Estado_producto',
        estado_por_defecto
    ).strip()

    # --------------------------------------------------------
    # VALIDAR TIPO
    # --------------------------------------------------------

    if not tipo_id:
        return None, 'Debe seleccionar un tipo de producto.'

    tipo = get_object_or_404(
        TiposProductos,
        ID_Tipo_producto=tipo_id,
    )

    if not tipo.Estado_tipo_producto:
        return None, 'No se pueden registrar productos con un tipo inactivo.'

    # --------------------------------------------------------
    # VALIDAR SUBTIPO
    # --------------------------------------------------------

    subtipos_disponibles = Subtipos.objects.filter(
        ID_Tipo_producto=tipo,
    )

    subtipo = None

    if subtipos_disponibles.exists():

        if not subtipo_id:
            return None, (
                'Debe seleccionar un subtipo para este tipo de producto.'
            )

        subtipo = subtipos_disponibles.filter(
            ID_Subtipo=subtipo_id
        ).first()

        if not subtipo:
            return None, (
                'El subtipo seleccionado no pertenece al tipo '
                'de producto elegido.'
            )

    elif subtipo_id:
        return None, (
            'El tipo de producto seleccionado no tiene subtipos disponibles.'
        )

    # --------------------------------------------------------
    # VALIDAR NOMBRE
    # --------------------------------------------------------

    if not nombre:
        return None, 'Debe ingresar el nombre del producto.'

    # --------------------------------------------------------
    # VALIDAR PRECIO
    # --------------------------------------------------------

    if not precio_input:
        return None, 'Debe ingresar el precio del producto.'

    try:
        precio = Decimal(precio_input)
    except (InvalidOperation, TypeError, ValueError):
        return None, 'El precio ingresado no es válido.'

    if not precio.is_finite() or precio <= 0:
        return None, 'El precio debe ser mayor a cero.'

    # --------------------------------------------------------
    # VALIDAR CANTIDAD DE PRESENTACIÓN
    # --------------------------------------------------------

    if cantidad_input:
        try:
            cantidad_presentacion = Decimal(cantidad_input)
        except (InvalidOperation, TypeError, ValueError):
            return None, (
                'La cantidad de presentación no es válida.'
            )

        if (
            not cantidad_presentacion.is_finite()
            or cantidad_presentacion <= 0
        ):
            return None, (
                'La cantidad de presentación debe ser mayor a cero.'
            )
    else:
        cantidad_presentacion = None

    # --------------------------------------------------------
    # VALIDAR STOCK MÍNIMO
    # --------------------------------------------------------

    stock_minimo_input = request.POST.get(
        'Stock_minimo', ''
    ).strip()

    if stock_minimo_input:
        try:
            stock_minimo = int(stock_minimo_input)
        except (ValueError, TypeError):
            return None, 'El stock mínimo ingresado no es válido.'

        if stock_minimo < 0:
            return None, 'El stock mínimo no puede ser negativo.'
    else:
        stock_minimo = None

    # --------------------------------------------------------
    # VALIDAR ESTADO
    # --------------------------------------------------------

    if estado_producto not in ('Activo', 'Inactivo'):
        return None, 'El estado del producto no es válido.'

    # --------------------------------------------------------
    # DATOS VALIDADOS
    # --------------------------------------------------------

    datos = {
        'stock_minimo': stock_minimo,
        'tipo': tipo,
        'subtipo': subtipo,
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
    """Comprueba si existe otro producto con el mismo nombre y marca."""

    productos = Productos.objects.filter(
        Nombre_producto__iexact=nombre
    )

    if marca:
        productos = productos.filter(
            Marca__iexact=marca
        )
    else:
        productos = productos.filter(
            Q(Marca__isnull=True) | Q(Marca='')
        )

    if excluir_pk is not None:
        productos = productos.exclude(
            ID_Producto=excluir_pk
        )

    return productos.exists()



def gestion_productos(request):
    """Lista, busca y filtra productos por tipo y subtipo."""

    usuario = usuario_con_acceso(request, 'productos')

    if not usuario:
        return redirect('login')

    busqueda = request.GET.get('q', '').strip()
    tipo_id = request.GET.get('tipo', '').strip()


    productos = Productos.objects.select_related(
        'ID_Tipo_producto',
        'ID_Subtipo',
        'stock'
    ).prefetch_related(
        Prefetch(
            'lotes',
            queryset=Lotes.objects.select_related(
                'ID_Remito',
                'ID_Remito__ID_Proveedor'
            ).order_by('Fecha_vencimiento', 'Numero_lote'),
            to_attr='lotes_ordenados'
        )
    ).annotate(
        num_lotes=Count('lotes')
    )

    # BÚSQUEDA
    if busqueda:
        productos = productos.filter(
            Q(Nombre_producto__icontains=busqueda) |
            Q(Descripcion_producto__icontains=busqueda) |
            Q(Marca__icontains=busqueda) |
            Q(
                ID_Tipo_producto__Nombre_tipo_producto__icontains=busqueda
            ) |
            Q(
                ID_Subtipo__Nombre_subtipo__icontains=busqueda
            )
        ).distinct()


    # FILTRO POR TIPO

    if tipo_id:

        productos = productos.filter(
            ID_Tipo_producto_id=tipo_id
        )


    # TIPOS Y SUBTIPOS PARA LOS FORMULARIOS

    tipos_productos = TiposProductos.objects.order_by(
        'Nombre_tipo_producto'
    )

    subtipos = Subtipos.objects.select_related(
        'ID_Tipo_producto'
    ).order_by(
        'Nombre_subtipo'
    )


    # MOSTRAR PRODUCTOS
    return render(
        request,
        'inventario/productos.html',
        {
            'productos': productos,
            'tipos_productos': tipos_productos,
            'subtipos': subtipos,
            'busqueda': busqueda,
            'usuario': usuario,
            'total_activos': Productos.objects.filter(
                Estado_producto='Activo'
            ).count(),
            'total_tipos': tipos_productos.count(),
        }
    )


def crear_producto(request):
    """Registra un producto con su tipo y subtipo correspondiente."""

    usuario = usuario_con_acceso(
        request,
        'productos',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para gestionar productos.'
        )
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_productos')

    datos, error = _leer_datos_producto(
        request,
        'Activo'
    )

    if error:
        messages.error(request, error)
        return redirect('gestion_productos')

    if _producto_duplicado(
        datos['nombre'],
        datos['marca']
    ):
        messages.error(
            request,
            'Ya existe un producto con esos datos.'
        )
        return redirect('gestion_productos')

    with transaction.atomic():

        producto = Productos.objects.create(
            ID_Tipo_producto=datos['tipo'],
            ID_Subtipo=datos['subtipo'],
            Marca=datos['marca'],
            Nombre_producto=datos['nombre'],
            Descripcion_producto=datos['descripcion'],
            Precio=datos['precio'],
            Cantidad_presentacion=datos['cantidad_presentacion'],
            Unidad_medida_producto=datos['unidad_medida'],
            Estado_producto=datos['estado_producto'],
        )

        # El stock inicial es cero.
        # Las entradas se registran mediante lotes.
        Stock.objects.get_or_create(
            ID_Producto=producto,
            defaults={
                'Cantidad_stock': 0,
                'Stock_minimo': datos['stock_minimo'] or 0,
            }
        )

        despues = snapshot(producto)

        stock_actual = Stock.objects.filter(
            ID_Producto=producto
        ).first()

        if stock_actual:
            despues['Stock_minimo'] = stock_actual.Stock_minimo

        registrar_auditoria(
            usuario=usuario,
            entidad='Productos',
            objeto=producto,
            accion='CREACION',
            antes={},
            despues=despues,
        )

    messages.success(
        request,
        'Producto registrado correctamente.'
    )

    return redirect('gestion_productos')


def editar_producto(request, pk):
    """Actualiza los datos del producto, incluido su subtipo."""

    usuario = usuario_con_acceso(
        request,
        'productos',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para gestionar productos.'
        )
        return redirect('panel_principal')

    producto = get_object_or_404(
        Productos,
        ID_Producto=pk
    )

    if request.method != 'POST':
        return redirect('gestion_productos')

    # --- AUDITORÍA: foto antes del cambio (incluye stock mínimo) ---
    stock_previo = Stock.objects.filter(ID_Producto=producto).first()
    antes = snapshot(producto)
    if stock_previo:
        antes['Stock_minimo'] = stock_previo.Stock_minimo

    datos, error = _leer_datos_producto(
        request,
        producto.Estado_producto
    )

    if error:
        messages.error(request, error)
        return redirect('gestion_productos')

    if _producto_duplicado(
        datos['nombre'],
        datos['marca'],
        excluir_pk=pk
    ):
        messages.error(
            request,
            'Ya existe otro producto con esos datos.'
        )
        return redirect('gestion_productos')

    with transaction.atomic():

        producto.ID_Tipo_producto = datos['tipo']
        producto.ID_Subtipo = datos['subtipo']
        producto.Marca = datos['marca']
        producto.Nombre_producto = datos['nombre']
        producto.Descripcion_producto = datos['descripcion']
        producto.Precio = datos['precio']
        producto.Cantidad_presentacion = datos['cantidad_presentacion']
        producto.Unidad_medida_producto = datos['unidad_medida']
        producto.Estado_producto = datos['estado_producto']
        

        producto.save()

        # Actualizar el stock mínimo sin modificar el stock actual.
        if datos['stock_minimo'] is not None:

            stock, creado = Stock.objects.get_or_create(
                ID_Producto=producto,
                defaults={
                    'Cantidad_stock': 0,
                    'Stock_minimo': datos['stock_minimo'],
                }
            )

            if not creado:
                stock.Stock_minimo = datos['stock_minimo']
                stock.save(
                    update_fields=['Stock_minimo']
                )

        # --- AUDITORÍA: foto después del cambio ---
        # refresh_from_db normaliza los decimales (1500.00 vs 1500)
        producto.refresh_from_db()
        despues = snapshot(producto)

        stock_actual = Stock.objects.filter(ID_Producto=producto).first()
        if stock_actual:
            despues['Stock_minimo'] = stock_actual.Stock_minimo

        registrar_auditoria(
            usuario,
            'Productos',
            producto,
            'MODIFICACION',
            antes,
            despues
        )

    messages.success(
        request,
        'Producto actualizado correctamente.'
    )

    return redirect('gestion_productos')


def eliminar_producto(request, pk):
    """Elimina un producto únicamente si no tiene lotes asociados."""

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_productos')

    producto = get_object_or_404(
        Productos,
        ID_Producto=pk
    )

    nombre = producto.Nombre_producto

    # No permitir eliminar productos que tengan lotes.
    if producto.lotes.exists():
        messages.error(
            request,
            f'No se puede eliminar el producto "{nombre}" porque tiene lotes asociados.'
        )
        return redirect('gestion_productos')

    try:
        with transaction.atomic():
            # Guardar los datos antes de eliminar.
            antes = snapshot(producto)

            stock = Stock.objects.filter(
                ID_Producto=producto
            ).first()

            if stock:
                antes['Stock_minimo'] = stock.Stock_minimo

            # Registrar la eliminación en la auditoría.
            registrar_auditoria(
                usuario=usuario,
                entidad='Productos',
                objeto=producto,
                accion='ELIMINACION',
                antes=antes,
                despues={},
            )

            # Eliminar el producto.
            producto.delete()

    except ProtectedError:
        messages.error(
            request,
            f'No se puede eliminar el producto "{nombre}" porque tiene otros registros asociados.'
        )
        return redirect('gestion_productos')

    messages.success(
        request,
        f'El producto "{nombre}" fue eliminado correctamente.'
    )

    return redirect('gestion_productos')


# ============================================================
# GESTIÓN DE LOTES
# ============================================================


def registrar_ingreso_lote(request):
    """Consulta de lotes. El alta se hace desde Remitos."""

    usuario = usuario_con_acceso(request, 'lotes')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para consultar lotes.'
        )
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()
    marca_filtro = request.GET.get('marca', '').strip()

    lotes = Lotes.objects.select_related(
        'ID_Producto',
        'ID_Remito',
        'ID_Remito__ID_Proveedor'
    ).order_by('-Fecha_ingreso', '-ID_Lote')

    if busqueda:
        lotes = lotes.filter(
            Q(Numero_lote__icontains=busqueda) |
            Q(ID_Producto__Nombre_producto__icontains=busqueda) |
            Q(ID_Remito__ID_Proveedor__nombre_proveedor__icontains=busqueda) |
            Q(ID_Remito__Numero_remito__icontains=busqueda)
        )

    if marca_filtro:
        lotes = lotes.filter(ID_Producto__Marca=marca_filtro)

    hoy = timezone.localdate()


    marcas = (
        Productos.objects
        .exclude(Marca__isnull=True)
        .exclude(Marca__exact='')
        .values_list('Marca', flat=True)
        .distinct()
        .order_by('Marca')
    )

    return render(
        request,
        'inventario/registrar_ingreso_lote.html',
        {
            'usuario': usuario,
            'lotes': lotes,
            'marcas': marcas,
            'busqueda': busqueda,
            'marca_filtro': marca_filtro,
            'hoy': hoy,
            'limite': hoy + timedelta(days=30),
        }
    )



# ============================================================
# MOVIMIENTOS DE STOCK
# ============================================================

def gestion_movimientos_stock(request):
    usuario = usuario_con_acceso(request, 'movimientos')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para consultar movimientos de stock.'
        )
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()
    tipo_sel = request.GET.get('tipo', '').strip()

    # Mostrar únicamente los movimientos permitidos.
    movimientos = MovimientosStock.objects.select_related(
        'ID_Usuario',
        'ID_Tipo_movimiento',
        'ID_Lote',
        'ID_Lote__ID_Producto',
        'ID_Lote__ID_Remito',
        'ID_Lote__ID_Remito__ID_Proveedor'
    ).filter(
        Q(
            ID_Tipo_movimiento__Nombre_tipo_movimiento__iexact='Entrada de lote'
        )
        | Q(
            ID_Tipo_movimiento__Nombre_tipo_movimiento__iexact='Salida por vencimiento de producto'
        )
    ).order_by('-Fecha_hora_movimiento')

    if busqueda:
        movimientos = movimientos.filter(
            Q(ID_Lote__ID_Producto__Nombre_producto__icontains=busqueda)
            | Q(ID_Lote__Numero_lote__icontains=busqueda)
            | Q(Observaciones__icontains=busqueda)
        )

    if tipo_sel:
        movimientos = movimientos.filter(
            ID_Tipo_movimiento_id=tipo_sel
        )

    # Mostrar solamente estos tipos en el filtro.
    todos_tipos = TiposMovimientos.objects.filter(
        Q(Nombre_tipo_movimiento__iexact='Entrada de lote')
        |   Q(
            Nombre_tipo_movimiento__iexact=
            'Salida por vencimiento de producto'
        )
    ).order_by('Nombre_tipo_movimiento')

    return render(
        request,
        'inventario/movimientos_stock.html',
        {
            'movimientos': movimientos,
            'todos_tipos': todos_tipos,
            'busqueda': busqueda,
            'tipo_sel': tipo_sel,
            'usuario': usuario,
            'activo': 'movimientos',
        }
    )


# ============================================================
# ALERTAS DE VENCIMIENTO
# ============================================================

def generar_alertas_vencimiento():
    fecha_actual = timezone.localdate()
    fecha_limite = fecha_actual + timedelta(days=30)

    lotes = Lotes.objects.select_related(
        'ID_Producto'
    ).filter(
        Fecha_vencimiento__isnull=False,
        Fecha_vencimiento__lte=fecha_limite,
        Cantidad_actual__gt=0
    ).order_by('Fecha_vencimiento')

    alertas_vencimiento = []

    for lote in lotes:
        dias_restantes = (
            lote.Fecha_vencimiento - fecha_actual
        ).days

        if dias_restantes < 0:
            mensaje = (
                f'El producto {lote.ID_Producto.Nombre_producto} '
                f'del lote {lote.Numero_lote} está vencido desde '
                f'el {lote.Fecha_vencimiento:%d/%m/%Y}.'
            )
        elif dias_restantes == 0:
            mensaje = (
                f'El producto {lote.ID_Producto.Nombre_producto} '
                f'del lote {lote.Numero_lote} vence hoy '
                f'({lote.Fecha_vencimiento:%d/%m/%Y}).'
            )
        else:
            mensaje = (
                f'El producto {lote.ID_Producto.Nombre_producto} '
                f'del lote {lote.Numero_lote} vence en '
                f'{dias_restantes} días '
                f'({lote.Fecha_vencimiento:%d/%m/%Y}).'
            )

        stock = Stock.objects.filter(
            ID_Producto=lote.ID_Producto
        ).first()

        if stock:
            nombre_producto = lote.ID_Producto.Nombre_producto

            # Arma el mensaje según el estado del vencimiento.
            if dias_restantes < 0:
                texto_vencimiento = (
                    f'está vencido desde el '
                    f'{lote.Fecha_vencimiento:%d/%m/%Y}.'
                )
            elif dias_restantes == 0:
                texto_vencimiento = (
                    f'vence hoy '
                    f'({lote.Fecha_vencimiento:%d/%m/%Y}).'
                )
            else:
                texto_vencimiento = (
                    f'vence en {dias_restantes} días '
                    f'({lote.Fecha_vencimiento:%d/%m/%Y}).'
                )

            mensaje_guardado = (
                f'El producto {nombre_producto} '
                f'del lote {lote.Numero_lote} '
                f'{texto_vencimiento} '
                f'[LOTE_ID:{lote.ID_Lote}]'
            )

            # Busca si ya existe una alerta para ese lote.
            alerta_existente = Alertas.objects.filter(
                ID_Stock=stock,
                Tipo_alerta='Vencimiento',
                Mensaje__contains=f'[LOTE_ID:{lote.ID_Lote}]'
            ).order_by('ID_Historial_alerta').first()

            if alerta_existente:
                # Actualiza el mensaje sin cambiar la fecha
                # de creación ni el estado de atención.
                if alerta_existente.Mensaje != mensaje_guardado:
                    alerta_existente.Mensaje = mensaje_guardado
                    alerta_existente.save(
                        update_fields=['Mensaje']
                    )
            else:
                # Registra una nueva alerta de vencimiento.
                Alertas.objects.create(
                    ID_Stock=stock,
                    Tipo_alerta='Vencimiento',
                    Mensaje=mensaje_guardado,
                    Cantidad_al_generar=lote.Cantidad_actual,
                    Stock_minimo_al_generar=stock.Stock_minimo,
                    Atendida=False
                )

        alertas_vencimiento.append({
            'producto': lote.ID_Producto,
            'lote': lote,
            'dias_restantes': dias_restantes,
            'mensaje': mensaje,
        })

    return alertas_vencimiento


def clave_fecha_alerta(item):
    fecha = item['fecha']

    if isinstance(fecha, datetime):
        return fecha.date()

    if isinstance(fecha, date):
        return fecha

    return date.min


# ============================================================
# HISTORIAL DE ALERTAS
# ============================================================

def gestion_alertas(request):
    usuario = usuario_con_acceso(request, 'alertas')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para consultar el historial de alertas.'
        )
        return redirect('panel_principal')

    tipo_alerta = request.GET.get('tipo', '').strip()
    producto_id = request.GET.get('producto', '').strip()
    usuario_id = request.GET.get('usuario', '').strip()
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()

    generar_alertas_vencimiento()

    alertas_bd = Alertas.objects.select_related(
        'ID_Stock',
        'ID_Stock__ID_Producto',
        'ID_Usuario'
    ).all()

    if tipo_alerta:
        alertas_bd = alertas_bd.filter(
            Tipo_alerta=tipo_alerta
        )

    if producto_id:
        alertas_bd = alertas_bd.filter(
            ID_Stock__ID_Producto_id=producto_id
        )

    if usuario_id:
        alertas_bd = alertas_bd.filter(
            ID_Usuario_id=usuario_id
        )

    if fecha_desde:
        alertas_bd = alertas_bd.filter(
            Fecha_hora_historial_alerta__date__gte=fecha_desde
        )

    if fecha_hasta:
        alertas_bd = alertas_bd.filter(
            Fecha_hora_historial_alerta__date__lte=fecha_hasta
        )

    alertas = []

    for alerta in alertas_bd:
        producto = alerta.ID_Stock.ID_Producto
        lote = None
        mensaje = alerta.Mensaje

        if alerta.Tipo_alerta == 'Vencimiento':
            try:
                marcador = mensaje.rsplit('[LOTE_ID:', 1)[1]
                lote_id = int(marcador.split(']', 1)[0])

                lote = Lotes.objects.filter(
                    ID_Lote=lote_id
                ).first()

            except (IndexError, ValueError):
                lote = None

            # Quita el identificador técnico del mensaje visible.
            mensaje = mensaje.split(' [LOTE_ID:', 1)[0]

        alertas.append({
            'id': alerta.ID_Historial_alerta,
            'tipo': alerta.Tipo_alerta,
            'producto': producto,
            'lote': lote,
            'mensaje': mensaje,
            'fecha': alerta.Fecha_hora_historial_alerta,
            'cantidad': alerta.Cantidad_al_generar,
            'stock_minimo': alerta.Stock_minimo_al_generar,
            'atendida': alerta.Atendida,
            'usuario': alerta.ID_Usuario,
            'fecha_atencion': alerta.Fecha_hora_atencion,
        })

    alertas.sort(
        key=clave_fecha_alerta,
        reverse=True
    )

    productos = Productos.objects.filter(
        Estado_producto='Activo'
    ).order_by('Nombre_producto')

    usuarios = Usuarios.objects.filter(
        Estado_usuario=True
    ).order_by(
        'Apellido_usuario',
        'Nombre_usuario'
    )

    return render(
        request,
        'inventario/historial_alertas.html',
        {
            'alertas': alertas,
            'tipo_alerta': tipo_alerta,
            'producto_id': producto_id,
            'usuario_id': usuario_id,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'productos': productos,
            'usuarios': usuarios,
            'usuario': usuario,
        }
    )


# ============================================================
# ATENDER ALERTAS
# ============================================================

@require_POST
def atender_alerta(request, id_alerta):
    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    alerta = get_object_or_404(
        Alertas,
        ID_Historial_alerta=id_alerta
    )

    if not alerta.Atendida:
        alerta.Atendida = True
        alerta.ID_Usuario = usuario
        alerta.Fecha_hora_atencion = timezone.now()

        alerta.save(update_fields=[
            'Atendida',
            'ID_Usuario',
            'Fecha_hora_atencion',
        ])

    return redirect('historial_alertas')


# ============================================================
# COMPROBANTE PDF DE MOVIMIENTO
# ============================================================

LOGO_STATIC = 'inventario/images/logo.png'


def _dibujar_logo(c, x, y, tam):
    """Logo vectorial de reemplazo: sol, hoja y monograma AV."""

    from math import cos, sin, radians

    c.saveState()

    # Sol con rayos (arriba a la derecha).
    cx = x + tam * 0.64
    cy = y + tam * 0.90

    c.setStrokeColor(colors.HexColor('#ffd54f'))
    c.setLineWidth(1.3)

    for grados in range(20, 181, 20):
        angulo = radians(grados)
        c.line(
            cx + cos(angulo) * tam * 0.15,
            cy + sin(angulo) * tam * 0.15,
            cx + cos(angulo) * tam * 0.24,
            cy + sin(angulo) * tam * 0.24,
        )

    c.setFillColor(colors.HexColor('#ffd54f'))
    c.circle(cx, cy, tam * 0.11, stroke=0, fill=1)

    # Hoja detrás de la V.
    hoja = c.beginPath()
    hoja.moveTo(x + tam * 0.42, y + tam * 0.02)
    hoja.curveTo(
        x + tam * 0.40, y + tam * 0.50,
        x + tam * 0.72, y + tam * 0.78,
        x + tam * 1.02, y + tam * 0.74
    )
    hoja.curveTo(
        x + tam * 1.04, y + tam * 0.36,
        x + tam * 0.80, y + tam * 0.06,
        x + tam * 0.42, y + tam * 0.02
    )
    hoja.close()

    c.setFillColor(colors.HexColor('#8bc34a'))
    c.drawPath(hoja, stroke=0, fill=1)

    # Monograma.
    c.setFillColor(colors.white)
    c.setFont('Times-BoldItalic', tam * 0.78)
    c.drawCentredString(x + tam * 0.48, y + tam * 0.18, 'AV')

    c.restoreState()


def _dibujar_comprobante(buffer, filas, logo_path=None, generado=''):
    """Dibuja el comprobante en un PDF A4 y lo escribe en buffer."""

    ancho, alto = A4

    verde_oscuro = colors.HexColor('#1b5e20')
    verde_claro = colors.HexColor('#4caf50')
    verde_medio = colors.HexColor('#2e7d32')
    fondo_etiqueta = colors.HexColor('#eaf4e6')
    fondo_fila_alt = colors.HexColor('#f6fbf4')
    linea = colors.HexColor('#dcebd9')
    borde = colors.HexColor('#c9e2c5')
    texto = colors.HexColor('#333333')

    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle('Comprobante de movimiento de stock')
    c.setAuthor('Agroquímica del Valle')

    # --------------------------------------------------------
    # ENCABEZADO CON DEGRADADO
    # --------------------------------------------------------

    alto_enc = 3.6 * cm
    y_enc = alto - alto_enc

    c.saveState()

    ruta = c.beginPath()
    ruta.rect(0, y_enc, ancho, alto_enc)
    c.clipPath(ruta, stroke=0, fill=0)

    c.linearGradient(
        0, y_enc, ancho, alto,
        (verde_medio, verde_claro)
    )

    # Círculos decorativos translúcidos.
    c.setFillColor(colors.white)
    c.setFillAlpha(0.07)
    c.circle(ancho * 0.30, y_enc + alto_enc * 0.35, 2.4 * cm, stroke=0, fill=1)
    c.circle(ancho * 0.72, y_enc + alto_enc * 0.20, 2.8 * cm, stroke=0, fill=1)

    c.restoreState()

    # Logo.
    x_logo = 2 * cm
    y_logo = y_enc + (alto_enc - 2.1 * cm) / 2

    logo_dibujado = False

    if logo_path:
        try:
            c.drawImage(
                ImageReader(logo_path),
                x_logo, y_logo,
                width=2.1 * cm, height=2.1 * cm,
                preserveAspectRatio=True,
                mask='auto'
            )
            logo_dibujado = True
        except Exception:
            logo_dibujado = False

    if not logo_dibujado:
        _dibujar_logo(c, x_logo, y_logo, 2.1 * cm)

    # Nombre de la empresa.
    x_texto = x_logo + 2.5 * cm

    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 15)
    c.drawString(x_texto, y_enc + alto_enc / 2 + 0.55 * cm, 'AGROQUÍMICA DEL')
    c.drawString(x_texto, y_enc + alto_enc / 2 - 0.05 * cm, 'VALLE')

    c.setFillColor(colors.HexColor('#e3f3e0'))
    c.setFont('Helvetica', 7.5)
    c.drawString(
        x_texto,
        y_enc + alto_enc / 2 - 0.62 * cm,
        'SISTEMA DE GESTIÓN DE STOCK'
    )

    # Título del documento (alineado a la derecha).
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 13)
    c.drawRightString(
        ancho - 2 * cm,
        y_enc + alto_enc / 2 + 0.3 * cm,
        'COMPROBANTE DE MOVIMIENTO DE'
    )
    c.drawRightString(
        ancho - 2 * cm,
        y_enc + alto_enc / 2 - 0.35 * cm,
        'STOCK'
    )

    # --------------------------------------------------------
    # TABLA DE DATOS
    # --------------------------------------------------------

    margen = 2 * cm
    ancho_tabla = ancho - 2 * margen
    ancho_col1 = ancho_tabla * 0.30
    ancho_col2 = ancho_tabla - ancho_col1

    tam_fuente = 9.5
    interlineado = 13
    padding = 12

    # Altura de cada fila según el texto (se parte en renglones).
    filas_calculadas = []

    for etiqueta, valor in filas:
        renglones = simpleSplit(
            str(valor),
            'Helvetica',
            tam_fuente,
            ancho_col2 - 2 * padding
        ) or ['']

        alto_fila = max(
            1.05 * cm,
            len(renglones) * interlineado + 2 * padding * 0.8
        )

        filas_calculadas.append((etiqueta, renglones, alto_fila))

    alto_total = sum(f[2] for f in filas_calculadas)

    y_tabla_top = y_enc - 1.5 * cm
    y_tabla_bottom = y_tabla_top - alto_total

    # Recorte con esquinas redondeadas.
    c.saveState()

    recorte = c.beginPath()
    recorte.roundRect(
        margen, y_tabla_bottom,
        ancho_tabla, alto_total,
        8
    )
    c.clipPath(recorte, stroke=0, fill=0)

    y = y_tabla_top

    for indice, (etiqueta, renglones, alto_fila) in enumerate(filas_calculadas):

        y_base = y - alto_fila

        # Fondo de la columna de etiquetas.
        c.setFillColor(fondo_etiqueta)
        c.rect(margen, y_base, ancho_col1, alto_fila, stroke=0, fill=1)

        # Fondo de la columna de valores (filas alternadas).
        c.setFillColor(fondo_fila_alt if indice % 2 else colors.white)
        c.rect(
            margen + ancho_col1, y_base,
            ancho_col2, alto_fila,
            stroke=0, fill=1
        )

        # Línea separadora.
        if indice < len(filas_calculadas) - 1:
            c.setStrokeColor(linea)
            c.setLineWidth(0.6)
            c.line(margen, y_base, margen + ancho_tabla, y_base)

        # Etiqueta.
        alto_texto = len(renglones) * interlineado
        primer_renglon = y - (alto_fila - alto_texto) / 2 - 9

        c.setFillColor(verde_oscuro)
        c.setFont('Helvetica-Bold', tam_fuente)
        c.drawString(margen + padding, primer_renglon, etiqueta)

        # Valor.
        c.setFillColor(texto)
        c.setFont('Helvetica', tam_fuente)

        for numero, renglon in enumerate(renglones):
            c.drawString(
                margen + ancho_col1 + padding,
                primer_renglon - numero * interlineado,
                renglon
            )

        y = y_base

    c.restoreState()

    # Borde exterior redondeado.
    c.setStrokeColor(borde)
    c.setLineWidth(0.9)
    c.roundRect(
        margen, y_tabla_bottom,
        ancho_tabla, alto_total,
        8, stroke=1, fill=0
    )

    # --------------------------------------------------------
    # PIE
    # --------------------------------------------------------

    c.setFillColor(colors.HexColor('#7a8a7a'))
    c.setFont('Helvetica', 8)
    c.drawCentredString(
        ancho / 2,
        y_tabla_bottom - 1.0 * cm,
        'Documento generado por el Sistema de Gestión de Stock.'
    )

    if generado:
        c.drawCentredString(
            ancho / 2,
            y_tabla_bottom - 1.45 * cm,
            f'Emitido el {generado}'
        )

    c.showPage()
    c.save()


def comprobante_movimiento_pdf(request, id_movimiento):

    usuario = usuario_con_acceso(
        request,
        'comprobantes',
        gestionar=True  
    )

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para emitir comprobantes.'
        )
        return redirect('panel_principal')
    
    movimiento = get_object_or_404(
        MovimientosStock.objects.select_related(
            'ID_Usuario',
            'ID_Tipo_movimiento',
            'ID_Lote',
            'ID_Lote__ID_Producto',
            'ID_Lote__ID_Producto__ID_Tipo_producto',
            'ID_Lote__ID_Producto__ID_Subtipo',
            'ID_Lote__ID_Remito',
            'ID_Lote__ID_Remito__ID_Proveedor',
        ),
        ID_Movimiento_stock=id_movimiento
    )

    # Pasar la fecha a la hora local (settings.TIME_ZONE) y darle
    # formato legible, sin microsegundos ni zona horaria.
    fecha_hora = movimiento.Fecha_hora_movimiento

    if timezone.is_aware(fecha_hora):
        fecha_hora = timezone.localtime(fecha_hora)

    filas = [
        ('N.º de movimiento:', str(movimiento.ID_Movimiento_stock)),
        (
            'Tipo de movimiento:',
            movimiento.ID_Tipo_movimiento.Nombre_tipo_movimiento
        ),
        ('Fecha:', fecha_hora.strftime('%d/%m/%Y')),
        ('Hora:', fecha_hora.strftime('%H:%M')),
    ]

    lote = movimiento.ID_Lote
    cantidad = movimiento.Cantidad_movimiento_stock

    if lote:
        producto = lote.ID_Producto

        filas.extend([
            ('Producto:', producto.Nombre_producto),
            ('Marca:', producto.Marca or 'No especificada'),
        ])

        if producto.ID_Tipo_producto:
            filas.append((
                'Tipo de producto:',
                producto.ID_Tipo_producto.Nombre_tipo_producto
            ))

        if producto.ID_Subtipo:
            filas.append((
                'Subtipo:',
                producto.ID_Subtipo.Nombre_subtipo
            ))

        filas.extend([
            ('Número de lote:', str(lote.Numero_lote)),
            (
                'Proveedor:',
                lote.ID_Remito.ID_Proveedor.nombre_proveedor
                if lote.ID_Remito and lote.ID_Remito.ID_Proveedor
                else 'No disponible'
            ),
            (
                'Número de remito:',
                lote.ID_Remito.Numero_remito
                if lote.ID_Remito
                else 'No disponible'
            ),
        ])

        if lote.Fecha_vencimiento:
            filas.append((
                'Fecha de vencimiento:',
                lote.Fecha_vencimiento.strftime('%d/%m/%Y')
            ))

    filas.append((
        'Cantidad:',
        f'{cantidad} unidad' if cantidad == 1 else f'{cantidad} unidades'
    ))

    if (
        lote
        and producto.Cantidad_presentacion
        and producto.Unidad_medida_producto
    ):
        filas.append((
            'Presentación:',
            f'{producto.Cantidad_presentacion.normalize():f} '
            f'{producto.Unidad_medida_producto}'
        ))

    filas.extend([
        ('Observaciones:', movimiento.Observaciones or 'Sin observaciones'),
        (
            'Usuario responsable:',
            movimiento.ID_Usuario.Usuario
            if movimiento.ID_Usuario else 'No disponible'
        ),
    ])

    buffer = BytesIO()

    _dibujar_comprobante(
        buffer,
        filas,
        logo_path=finders.find(LOGO_STATIC),
        generado=timezone.localtime().strftime('%d/%m/%Y %H:%M')
    )

    pdf = buffer.getvalue()
    buffer.close()

    respuesta = HttpResponse(
        pdf,
        content_type='application/pdf'
    )

    respuesta['Content-Disposition'] = (
        f'inline; filename="comprobante_movimiento_{id_movimiento}.pdf"'
    )
    respuesta['Content-Length'] = len(pdf)

    return respuesta



def gestion_remitos(request):
    usuario = usuario_con_acceso(
        request,
        'remitos',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para gestionar remitos.'
        )
        return redirect('panel_principal')

    hoy = timezone.localdate()

    if request.method == 'POST':
        accion = request.POST.get('accion', '').strip()

        # ====================================================
        # REGISTRAR REMITO CON SUS LOTES
        # ====================================================
        if accion == 'crear_remito':
            proveedor_id = request.POST.get('ID_Proveedor', '').strip()
            numero_remito = request.POST.get('Numero_remito', '').strip()
            fecha_texto = request.POST.get('Fecha_remito', '').strip()

            productos_ids = request.POST.getlist('lote_producto')
            numeros_lote = request.POST.getlist('lote_numero')
            vencimientos = request.POST.getlist('lote_vencimiento')
            cantidades = request.POST.getlist('lote_cantidad')

            if not proveedor_id or not numero_remito or not fecha_texto:
                messages.error(request, 'Completá los datos del remito.')
                return redirect('gestion_remitos')

            if not (
                len(productos_ids) == len(numeros_lote)
                == len(vencimientos) == len(cantidades)
            ) or not productos_ids:
                messages.error(
                    request,
                    'Agregá al menos un lote y completá todos sus datos.'
                )
                return redirect('gestion_remitos')

            if len(numero_remito) > 20:
                messages.error(
                    request,
                    'El número de remito no puede superar los 20 caracteres.'
                )
                return redirect('gestion_remitos')

            try:
                fecha_remito = date.fromisoformat(fecha_texto)
            except ValueError:
                messages.error(request, 'La fecha del remito no es válida.')
                return redirect('gestion_remitos')

            if fecha_remito > hoy:
                messages.error(
                    request,
                    'La fecha del remito no puede ser futura.'
                )
                return redirect('gestion_remitos')

            proveedor = Proveedores.objects.filter(
                ID_Proveedor=proveedor_id,
                estado_proveedor=True
            ).first()

            if not proveedor:
                messages.error(
                    request,
                    'El proveedor seleccionado no existe o está inactivo.'
                )
                return redirect('gestion_remitos')
            
    

            # Validar los lotes antes de guardar.
            lotes_validados = []
            combinaciones = set()

            for producto_id, numero_lote, vencimiento_texto, cantidad_texto in zip(
                productos_ids, numeros_lote, vencimientos, cantidades
            ):
                numero_lote = numero_lote.strip()

                if not all([
                    producto_id,
                    numero_lote,
                    vencimiento_texto,
                    cantidad_texto
                ]):
                    messages.error(
                        request,
                        'Completá todos los campos de cada lote.'
                    )
                    return redirect('gestion_remitos')

                if len(numero_lote) > 50:
                    messages.error(
                        request,
                        'El número de lote no puede superar los 50 caracteres.'
                    )
                    return redirect('gestion_remitos')

                try:
                    cantidad = int(cantidad_texto)
                    fecha_vencimiento = date.fromisoformat(
                        vencimiento_texto
                    )
                except (ValueError, TypeError):
                    messages.error(
                        request,
                        'Revisá las cantidades y las fechas de los lotes.'
                    )
                    return redirect('gestion_remitos')

                if cantidad <= 0:
                    messages.error(
                        request,
                        'La cantidad de cada lote debe ser mayor a cero.'
                    )
                    return redirect('gestion_remitos')

                if fecha_vencimiento < hoy:
                    messages.error(
                        request,
                        'No se pueden registrar lotes ya vencidos.'
                    )
                    return redirect('gestion_remitos')
                
                if fecha_vencimiento < fecha_remito:
                    messages.error(
                        request,
                        'La fecha de vencimiento no puede ser anterior '
                        'a la fecha del remito.'
                    )
                    return redirect('gestion_remitos')

                producto = Productos.objects.filter(
                    ID_Producto=producto_id,
                    Estado_producto='Activo'
                ).first()

                if not producto:
                    messages.error(
                        request,
                        'Uno de los productos seleccionados no existe '
                        'o está inactivo.'
                    )
                    return redirect('gestion_remitos')
                
                
            # Verificar si el lote ya existe en la base de datos.
                if Lotes.objects.filter(
                    ID_Producto=producto,
                    Numero_lote=numero_lote
                ).exists():
                    messages.error(
                        request,
                        f'El lote "{numero_lote}" ya existe para '
                        f'el producto "{producto.Nombre_producto}".'
                    )
                    return redirect('gestion_remitos')


                combinacion = (producto.pk, numero_lote)

                if combinacion in combinaciones:
                    messages.error(
                        request,
                        'No podés repetir el número de lote para el mismo producto.'
                    )
                    return redirect('gestion_remitos')

                combinaciones.add(combinacion)

                lotes_validados.append({
                    'producto': producto,
                    'numero': numero_lote,
                    'vencimiento': fecha_vencimiento,
                    'cantidad': cantidad,
                })

            tipo_entrada = TiposMovimientos.objects.filter(
                Nombre_tipo_movimiento__iexact='Entrada de lote'
            ).first()

            if not tipo_entrada:
                messages.error(
                    request,
                    'Falta registrar el tipo de movimiento "Entrada de lote".'
                )
                return redirect('gestion_remitos')

            # Todo se guarda junto: si algo falla, se revierte todo.
            try:
                with transaction.atomic():
                    remito = Remitos.objects.create(
                        ID_Proveedor=proveedor,
                        Numero_remito=numero_remito,
                        Fecha_remito=fecha_remito
                    )

                    for datos in lotes_validados:
                        lote = Lotes.objects.create(
                            ID_Remito=remito,
                            ID_Producto=datos['producto'],
                            Numero_lote=datos['numero'],
                            Cantidad_ingresada=datos['cantidad'],
                            Cantidad_actual=datos['cantidad'],
                            Fecha_ingreso=hoy,
                            Fecha_vencimiento=datos['vencimiento']
                        )

                        stock, creado = (
                            Stock.objects.select_for_update().get_or_create(
                                ID_Producto=datos['producto'],
                                defaults={
                                    'Cantidad_stock': 0,
                                    'Stock_minimo': 10
                                }
                            )
                        )

                        stock.Cantidad_stock += datos['cantidad']
                        stock.save(update_fields=['Cantidad_stock'])

                        MovimientosStock.objects.create(
                            ID_Usuario=usuario,
                            ID_Tipo_movimiento=tipo_entrada,
                            ID_Lote=lote,
                            Cantidad_movimiento_stock=datos['cantidad'],
                            Observaciones=(
                                f'Entrada por remito {numero_remito}'
                            )
                        )

                messages.success(
                    request,
                    'El remito, sus lotes, el stock y los movimientos '
                    'se registraron correctamente.'
                )

            except IntegrityError:
                messages.error(
                    request,
                    'El número de remito ya existe para ese proveedor, '
                    'o uno de los lotes está duplicado para el producto.'
                )

            except DatabaseError:
                messages.error(
                    request,
                    'Ocurrió un error en la base de datos. '
                    'No se guardaron los cambios.'
                )

            return redirect('gestion_remitos')


        # ====================================================
        # EDITAR DATOS DEL REMITO
        # ====================================================
        elif accion == 'editar_remito':
            remito_id = request.POST.get('ID_Remito', '').strip()
            numero_remito = request.POST.get('Numero_remito', '').strip()
            fecha_texto = request.POST.get('Fecha_remito', '').strip()

            if not remito_id or not numero_remito or not fecha_texto:
                messages.error(
                    request,
                    'Completá todos los campos del remito.'
                )
                return redirect('gestion_remitos')

            # Validar la longitud del número de remito.
            if len(numero_remito) > 20:
                messages.error(
                    request,
                    'El número de remito no puede superar los 20 caracteres.'
                )
                return redirect('gestion_remitos')

            try:
                fecha_remito = date.fromisoformat(fecha_texto)
            except ValueError:
                messages.error(
                    request,
                    'La fecha del remito no es válida.'
                )
                return redirect('gestion_remitos')

            if fecha_remito > hoy:
                messages.error(
                    request,
                    'La fecha del remito no puede ser futura.'
                )
                return redirect('gestion_remitos')

            try:
                remito = Remitos.objects.get(ID_Remito=remito_id)
                antes = snapshot(remito)
                remito.Numero_remito = numero_remito
                remito.Fecha_remito = fecha_remito
                remito.save(
                    update_fields=['Numero_remito', 'Fecha_remito']
                )

                registrar_auditoria(usuario, 'Remitos', remito, 'MODIFICACION', antes, snapshot(remito))

                messages.success(
                    request,
                    'El remito se actualizó correctamente.'
                )

            except Remitos.DoesNotExist:
                messages.error(
                    request,
                    'El remito seleccionado no existe.'
                )

            except IntegrityError:
                messages.error(
                    request,
                    'Ya existe otro remito con ese número para el proveedor.'
                )

            return redirect('gestion_remitos')
        
       
      
        # ====================================================
        # EDITAR DATOS DEL LOTE
        # ====================================================
        elif accion == 'editar_lote':
            lote_id = request.POST.get('ID_Lote', '').strip()
            producto_id = request.POST.get('ID_Producto', '').strip()
            numero_lote = request.POST.get('Numero_lote', '').strip()
            cantidad_ingresada_texto = request.POST.get(
                'Cantidad_ingresada', ''
            ).strip()
            cantidad_actual_texto = request.POST.get(
                'Cantidad_actual', ''
            ).strip()
            fecha_ingreso_texto = request.POST.get(
                'Fecha_ingreso', ''
            ).strip()
            vencimiento_texto = request.POST.get(
                'Fecha_vencimiento', ''
            ).strip()

            if not all([
                lote_id, producto_id, numero_lote,
                cantidad_ingresada_texto, cantidad_actual_texto,
                fecha_ingreso_texto, vencimiento_texto
            ]):
                messages.error(request, 'Completá todos los campos del lote.')
                return redirect('gestion_remitos')

            if len(numero_lote) > 50:
                messages.error(
                    request,
                    'El número de lote no puede superar los 50 caracteres.'
                )
                return redirect('gestion_remitos')

            try:
                cantidad_ingresada = int(cantidad_ingresada_texto)
                cantidad_actual = int(cantidad_actual_texto)
                fecha_ingreso = date.fromisoformat(fecha_ingreso_texto)
                fecha_vencimiento = date.fromisoformat(vencimiento_texto)
            except (ValueError, TypeError):
                messages.error(
                    request,
                    'Revisá las cantidades y las fechas ingresadas.'
                )
                return redirect('gestion_remitos')

            if cantidad_ingresada <= 0:
                messages.error(
                    request,
                    'La cantidad ingresada debe ser mayor a cero.'
                )
                return redirect('gestion_remitos')

            if not 0 <= cantidad_actual <= cantidad_ingresada:
                messages.error(
                    request,
                    'La cantidad actual debe estar entre cero y la cantidad ingresada.'
                )
                return redirect('gestion_remitos')

            if fecha_ingreso > hoy:
                messages.error(
                    request,
                    'La fecha de ingreso no puede ser futura.'
                )
                return redirect('gestion_remitos')

            if fecha_vencimiento < fecha_ingreso:
                messages.error(
                    request,
                    'El vencimiento no puede ser anterior al ingreso.'
                )
                return redirect('gestion_remitos')

            try:
                with transaction.atomic():
                    lote = Lotes.objects.select_for_update().select_related(
                        'ID_Producto', 'ID_Remito'
                    ).get(ID_Lote=lote_id)

                    producto = Productos.objects.filter(
                        ID_Producto=producto_id,
                        Estado_producto='Activo'
                    ).first()

                    if not producto:
                        messages.error(
                            request,
                            'El producto seleccionado no existe o está inactivo.'
                        )
                        return redirect('gestion_remitos')

                    duplicado = Lotes.objects.filter(
                        ID_Producto=producto,
                        Numero_lote=numero_lote
                    ).exclude(ID_Lote=lote.ID_Lote).exists()

                    if duplicado:
                        messages.error(
                            request,
                            'Ya existe ese número de lote para el producto.'
                        )
                        return redirect('gestion_remitos')

                    # Buscar el movimiento de entrada original.
                    tipo_entrada = TiposMovimientos.objects.filter(
                        Nombre_tipo_movimiento__iexact='Entrada de lote'
                    ).first()

                    if not tipo_entrada:
                        messages.error(
                            request,
                            'No existe el tipo de movimiento "Entrada de lote".'
                        )
                        return redirect('gestion_remitos')

                    entradas = MovimientosStock.objects.filter(
                        ID_Lote=lote,
                        ID_Tipo_movimiento=tipo_entrada
                    )

                    entrada = entradas.select_for_update().first()

                    if not entrada:
                        messages.error(
                            request,
                            'No se encontró el movimiento de entrada del lote.'
                        )
                        return redirect('gestion_remitos')

                    # Verificar que no existan movimientos posteriores.
                    otros_movimientos = MovimientosStock.objects.filter(
                        ID_Lote=lote
                    ).exclude(
                        ID_Movimiento_stock=entrada.ID_Movimiento_stock
                    ).exists()

                    cambio_producto = lote.ID_Producto_id != producto.pk
                    if cambio_producto:
                        messages.error(
                            request,
                            'No se puede cambiar el producto de un lote que ya tiene '
                            'un movimiento de entrada registrado.'
                        )
                        return redirect('gestion_remitos')

                    cambio_cantidades = (
                        lote.Cantidad_ingresada != cantidad_ingresada
                        or lote.Cantidad_actual != cantidad_actual
                    )

                    if otros_movimientos and (cambio_producto or cambio_cantidades):
                        messages.error(
                            request,
                            'No se puede cambiar el producto o las cantidades '
                            'porque el lote tiene otros movimientos registrados.'
                        )
                        return redirect('gestion_remitos')

                    # La corrección de cantidades solo se permite
                    # si el lote conserva únicamente su entrada original.
                    if cambio_cantidades and (
                        lote.Cantidad_actual != lote.Cantidad_ingresada
                    ):
                        messages.error(
                            request,
                            'No se pueden corregir las cantidades porque '
                            'la cantidad actual ya es diferente de la ingresada.'
                        )
                        return redirect('gestion_remitos')

                    antes = snapshot(lote)
                    if cambio_cantidades:
                        cantidad_actual = cantidad_ingresada
                    else:
                        cantidad_actual = lote.Cantidad_actual

                    # Actualizar el stock por la diferencia de entrada.
                    if cambio_cantidades:
                        diferencia = (
                            cantidad_ingresada - lote.Cantidad_ingresada
                        )

                        stock = Stock.objects.select_for_update().filter(
                            ID_Producto=lote.ID_Producto
                        ).first()

                        if not stock:
                            messages.error(
                                request,
                                'No se encontró el stock del producto.'
                            )
                            return redirect('gestion_remitos')


                        if stock.Cantidad_stock + diferencia < 0:
                            messages.error(
                                request,
                                'La corrección dejaría el stock general en negativo.'
                            )
                            return redirect('gestion_remitos')

                        stock.Cantidad_stock += diferencia
                        stock.save(update_fields=['Cantidad_stock'])

                        # Actualizar el movimiento de entrada existente.
                        entrada.Cantidad_movimiento_stock = cantidad_ingresada
                        entrada.save(
                            update_fields=['Cantidad_movimiento_stock']
                        )

                    lote.ID_Producto = producto
                    lote.Numero_lote = numero_lote
                    lote.Cantidad_ingresada = cantidad_ingresada
                    lote.Cantidad_actual = cantidad_actual
                    lote.Fecha_ingreso = fecha_ingreso
                    lote.Fecha_vencimiento = fecha_vencimiento
                    lote.save()

                    registrar_auditoria(
                        usuario,
                        'Lotes',
                        lote,
                        'MODIFICACION',
                        antes,
                        snapshot(lote)
                    )

                messages.success(
                    request,
                    'Los datos del lote se actualizaron correctamente.'
                )

            except Lotes.DoesNotExist:
                messages.error(request, 'El lote seleccionado no existe.')

            except IntegrityError:
                messages.error(
                    request,
                    'No se pudo actualizar el lote por datos duplicados '
                    'o una restricción de la base de datos.'
                )

            except DatabaseError:
                messages.error(
                    request,
                    'Ocurrió un error en la base de datos. No se guardaron los cambios.'
                )

            return redirect('gestion_remitos')

        # Si la acción recibida no es válida.
        messages.error(request, 'La operación solicitada no es válida.')
        return redirect('gestion_remitos')



    # ========================================================
    # GET: CONSULTAR Y FILTRAR REMITOS
    # ========================================================
    remitos = (
        Remitos.objects
        .select_related('ID_Proveedor')
        .prefetch_related('lotes__ID_Producto')
        .order_by('-Fecha_remito', '-ID_Remito')
    )

    busqueda = request.GET.get('q', '').strip()
    proveedor_filtro = request.GET.get('proveedor', '').strip()

    if busqueda:
        remitos = remitos.filter(
            Q(Numero_remito__icontains=busqueda)
            | Q(ID_Proveedor__nombre_proveedor__icontains=busqueda)
        )

    if proveedor_filtro:
        remitos = remitos.filter(
            ID_Proveedor__ID_Proveedor=proveedor_filtro
        )

    proveedores = Proveedores.objects.filter(
        estado_proveedor=True
    ).order_by('nombre_proveedor')

    productos_alta = Productos.objects.filter(
        Estado_producto='Activo'
    ).order_by('Nombre_producto')

    return render(
        request,
        'inventario/gestion_remitos.html',
        {
            'usuario': usuario,
            'remitos': remitos,
            'proveedores': proveedores,
            'proveedores_alta': proveedores,
            'productos_alta': productos_alta,
            'total_remitos': Remitos.objects.count(),
            'total_proveedores': Remitos.objects.values(
                'ID_Proveedor'
            ).distinct().count(),
            'total_lotes': Lotes.objects.count(),
            'busqueda': busqueda,
            'proveedor_filtro': proveedor_filtro,
            'hoy': hoy,
        }
    )



@require_POST
def eliminar_proveedor(request, pk):

    if not usuario_es_administrador(request):
        return redirect('panel_principal')

    proveedor = get_object_or_404(Proveedores, ID_Proveedor=pk)
    nombre = proveedor.nombre_proveedor

    try:
        with transaction.atomic():
            proveedor.delete()
    except ProtectedError:
        messages.error(
            request,
            f'No se puede eliminar el proveedor "{nombre}": '
            'tiene remitos registrados.'
        )
        return redirect('gestion_proveedores')

    messages.success(request, f'El proveedor "{nombre}" fue eliminado.')

    return redirect('gestion_proveedores')


@require_POST
def eliminar_usuario(request, pk):

    admin = usuario_es_administrador(request)

    if not admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(Usuarios, ID_Usuario=pk)

    if usuario.ID_Usuario == admin.ID_Usuario:
        messages.error(request, 'No puede eliminarse a sí mismo.')
        return redirect('gestion_usuarios')

    nombre = usuario.Usuario

    try:
        with transaction.atomic():
            usuario.delete()
    except ProtectedError:
        messages.error(
            request,
            f'No se puede eliminar al usuario "{nombre}": tiene '
            'movimientos o alertas registrados.'
        )
        return redirect('gestion_usuarios')

    messages.success(request, f'El usuario "{nombre}" fue eliminado.')

    return redirect('gestion_usuarios')


@require_POST
def eliminar_perfil(request, pk):

    usuario = usuario_es_administrador(request)

    if not usuario:
        return redirect('panel_principal')

    perfil = get_object_or_404(Perfiles, ID_Perfil=pk)
    nombre = perfil.Nombre_perfil

    if nombre in PERFILES_ADMIN:
        messages.error(
            request,
            'No se puede eliminar un perfil de sistema.'
        )
        return redirect('gestion_perfiles')

    if perfil.ID_Perfil == usuario.ID_Perfil.ID_Perfil:
        messages.error(
            request,
            'No puede eliminar el perfil con el que inició sesión.'
        )
        return redirect('gestion_perfiles')

    try:
        with transaction.atomic():
            perfil.delete()     # sus permisos asignados se borran en cascada
    except ProtectedError:
        messages.error(
            request,
            f'No se puede eliminar el perfil "{nombre}": '
            'hay usuarios asignados.'
        )
        return redirect('gestion_perfiles')

    messages.success(request, f'El perfil "{nombre}" fue eliminado.')

    return redirect('gestion_perfiles')

# ============================================================
# AUDITORÍA (solo Administrador)
# ============================================================

def _fecha_iso(texto):
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _inicio_dia(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def gestion_auditoria(request):

    usuario = usuario_es_administrador(request)

    if not usuario:
        messages.error(
            request,
            'Solo el administrador puede consultar la auditoría.'
        )
        return redirect('panel_principal')

    entidad = request.GET.get('entidad', '').strip()
    accion = request.GET.get('accion', '').strip()
    usuario_id = request.GET.get('usuario', '').strip()
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()

    logs = LogAuditoria.objects.select_related(
        'ID_Usuario'
    ).order_by('-Fecha_hora')
    
    if entidad:
        logs = logs.filter(Entidad=entidad)

    if accion:
        logs = logs.filter(Accion=accion)

    if usuario_id.isdigit():
        logs = logs.filter(ID_Usuario_id=usuario_id)

    desde = _fecha_iso(fecha_desde)
    hasta = _fecha_iso(fecha_hasta)

    if desde:
        logs = logs.filter(Fecha_hora__gte=_inicio_dia(desde))

    if hasta:
        logs = logs.filter(
            Fecha_hora__lt=_inicio_dia(hasta + timedelta(days=1))
        )

    pagina = Paginator(logs, 50).get_page(request.GET.get('page'))

    return render(
        request,
        'inventario/auditoria.html',
        {
            'usuario': usuario,
            'pagina': pagina,
            'entidades': LogAuditoria.objects.values_list(
                'Entidad', flat=True
            ).distinct(),
            'usuarios': Usuarios.objects.order_by(
                'Apellido_usuario', 'Nombre_usuario'
            ),
            'entidad': entidad,
            'accion': accion,
            'usuario_id': usuario_id,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'activo': 'auditoria',
        }
    )

def detalle_auditoria(request, id_log):
    usuario = usuario_es_administrador(request)

    if not usuario:
        return JsonResponse(
            {'error': 'No tenés permiso para consultar la auditoría.'},
            status=403
        )

    log = get_object_or_404(LogAuditoria, pk=id_log)

    return JsonResponse({
        'id': log.ID_Log,
        'fecha': log.Fecha_hora.strftime('%d/%m/%Y'),
        'hora': log.Fecha_hora.strftime('%H:%M'),
        'usuario': (
            f'{log.ID_Usuario.Apellido_usuario}, '
            f'{log.ID_Usuario.Nombre_usuario}'
            if log.ID_Usuario else 'Sistema'
        ),
        'perfil': log.Perfil_usuario or 'Sin perfil',
        'entidad': log.Entidad,
        'registro': log.ID_Registro,
        'accion': log.Accion,
        'anteriores': log.Valores_anteriores or {},
        'actuales': log.Valores_actuales or {},
        'cambios': [
            {
                'campo': campo,
                'antes': antes,
                'despues': despues
            }
            for campo, antes, despues in log.cambios
        ]
    })