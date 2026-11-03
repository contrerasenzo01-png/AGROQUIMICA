import re
import time as time_module
import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.utils.http import url_has_allowed_host_and_scheme

from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.http import JsonResponse
from django.contrib.staticfiles import finders
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.urls import reverse

from django.db.models import Count, F, Prefetch, ProtectedError, Q, RestrictedError, Sum
from django.db.models.functions import Coalesce

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas
from .reportes import generar_reportes, datos_evolucion_rango
from .pdf_remito import generar_pdf_remito
from .alertas import (
    DIAS_AVISO_VENCIMIENTO, TIPO_STOCK, TIPOS_STOCK,
    listar_notificaciones, mensaje_visible, revisar_stock,
    revisar_vencimientos as generar_alertas_vencimiento,
)
from .auditoria import (
    snapshot, registrar_auditoria, accion_por_estado,
    registrar_asignacion_perfil, registrar_asignacion_permisos,
)
from .forms import ProveedorForm
from .permissions import (
    usuario_con_acceso, usuario_con_accion, puede, puede_accion,
    catalogo_plano, permisos_asignados, PERFILES_ADMIN,
)

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

from .recuperacion import (
    enviar_correo_recuperacion, limite_superado,
    token_valido, usuario_desde_uid, usuario_habilitado,
)

# ============================================================
# CONTROL DE ACCESO
# Los permisos se verifican en permissions.py.
# PERFILES_ADMIN se importa de ahí para tenerlo en un solo lugar.
# ============================================================

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
                request.session['bloqueada'] = False
                request.session['ultima_actividad'] = time_module.time()
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

def _clase_movimiento(nombre_tipo):
    """Clase visual y signo de un movimiento según su tipo."""

    nombre = (nombre_tipo or '').lower()

    # La anulación de un egreso DEVUELVE stock: suma, como una entrada.
    if 'anulaci' in nombre and 'egreso' in nombre:
        return 'entrada', 1
    if 'entrada' in nombre:
        return 'entrada', 1
    if 'vencimiento' in nombre:
        return 'vencimiento', -1
    if 'anulaci' in nombre:
        return 'anulacion', -1

    return 'salida', -1


def _datos_panel(usuario):
    """Arma los datos del panel principal para el componente React.

    Cada bloque solo se incluye si el perfil del usuario puede
    ver ese módulo, así el panel respeta los mismos permisos
    que el menú lateral.
    """

    ver_usuarios = puede(usuario, 'usuarios')
    ver_productos = puede(usuario, 'productos')
    ver_movimientos = puede(usuario, 'movimientos')
    ver_alertas = puede(usuario, 'alertas')
    ver_lotes = puede(usuario, 'lotes')
    emitir_comprobantes = puede(usuario, 'comprobantes', gestionar=True)

    # Actualiza las alertas de vencimiento y devuelve los lotes
    # que vencen en los próximos 30 días (o ya vencieron con stock).
    lotes_vencimiento = generar_alertas_vencimiento()

    metricas = []
    stock_bajo = []
    por_vencer = []
    grafico = []
    movimientos = []

    # ---------------- PRODUCTOS Y STOCK ----------------
    if ver_productos:
        stocks_bajos = Stock.objects.select_related(
            'ID_Producto'
        ).filter(
            ID_Producto__Estado_producto='Activo',
            Cantidad_stock__lte=F('Stock_minimo')
        ).order_by('Cantidad_stock', 'ID_Producto__Nombre_producto')

        stock_bajo = [
            {
                'id': s.ID_Producto_id,
                'producto': s.ID_Producto.Nombre_producto,
                'stock': s.Cantidad_stock,
                'minimo': s.Stock_minimo,
            }
            for s in stocks_bajos
        ]

        productos_con_stock = Stock.objects.filter(
            ID_Producto__Estado_producto='Activo',
            Cantidad_stock__gt=0
        ).count()

        metricas.append({
            'clave': 'productos',
            'titulo': 'Productos con stock',
            'valor': productos_con_stock,
            'detalle': 'productos activos',
            'color': 'blue',
            'url': reverse('gestion_productos'),
        })

        metricas.append({
            'clave': 'stock_bajo',
            'titulo': 'Stock bajo / crítico',
            'valor': len(stock_bajo),
            'detalle': 'en o bajo el mínimo',
            'color': 'red',
            'url': reverse('gestion_productos'),
        })

        # Productos activos agrupados por subtipo (o por tipo si no tiene).
        conteo = {}

        for producto in Productos.objects.filter(
            Estado_producto='Activo'
        ).select_related('ID_Tipo_producto', 'ID_Subtipo'):
            if producto.ID_Subtipo:
                nombre = producto.ID_Subtipo.Nombre_subtipo
            else:
                nombre = producto.ID_Tipo_producto.Nombre_tipo_producto

            conteo[nombre] = conteo.get(nombre, 0) + 1

        grafico = sorted(
            [{'nombre': n, 'cantidad': c} for n, c in conteo.items()],
            key=lambda d: (-d['cantidad'], d['nombre'])
        )

    # ---------------- LOTES POR VENCER ----------------
    if ver_productos or ver_lotes:
        por_vencer = [
            {
                'id': item['lote'].ID_Lote,
                'producto': item['producto'].Nombre_producto,
                'lote': item['lote'].Numero_lote,
                'dias': item['dias_restantes'],
                'vence': item['lote'].Fecha_vencimiento.strftime('%d/%m/%Y'),
                'cantidad': item['lote'].Cantidad_actual,
            }
            for item in lotes_vencimiento
        ]

        metricas.append({
            'clave': 'por_vencer',
            'titulo': 'Lotes por vencer',
            'valor': len([l for l in por_vencer if l['dias'] >= 0]),
            'detalle': 'en los próximos 30 días',
            'color': 'orange',
            'url': reverse('registrar_ingreso_lote') if ver_lotes else '',
        })

    # ---------------- ALERTAS ----------------
    if ver_alertas:
        metricas.append({
            'clave': 'alertas',
            'titulo': 'Alertas sin atender',
            'valor': Alertas.objects.filter(Atendida=False).count(),
            'detalle': 'stock bajo y vencimientos',
            'color': 'orange',
            'url': reverse('historial_alertas'),
        })

    # ---------------- USUARIOS ----------------
    if ver_usuarios:
        metricas.insert(0, {
            'clave': 'usuarios',
            'titulo': 'Usuarios activos',
            'valor': Usuarios.objects.filter(Estado_usuario=True).count(),
            'detalle': 'con acceso al sistema',
            'color': 'green',
            'url': reverse('gestion_usuarios'),
        })

    # ---------------- ÚLTIMOS MOVIMIENTOS ----------------
    if ver_movimientos:
        ultimos = MovimientosStock.objects.select_related(
            'ID_Tipo_movimiento',
            'ID_Lote',
            'ID_Lote__ID_Producto',
            'ID_Usuario',
        ).order_by('-Fecha_hora_movimiento')[:8]

        for mov in ultimos:
            nombre_tipo = mov.ID_Tipo_movimiento.Nombre_tipo_movimiento
            clase, signo = _clase_movimiento(nombre_tipo)
            fecha = timezone.localtime(mov.Fecha_hora_movimiento)

            movimientos.append({
                'id': mov.ID_Movimiento_stock,
                'fecha': fecha.strftime('%d/%m/%Y'),
                'hora': fecha.strftime('%H:%M'),
                'producto': (
                    mov.ID_Lote.ID_Producto.Nombre_producto
                    if mov.ID_Lote else '—'
                ),
                'lote': mov.ID_Lote.Numero_lote if mov.ID_Lote else '',
                'tipo': nombre_tipo,
                'clase': clase,
                'cantidad': signo * mov.Cantidad_movimiento_stock,
                'observaciones': mov.Observaciones or '',
                'usuario': mov.ID_Usuario.Usuario if mov.ID_Usuario else '',
                'comprobante': (
                    reverse('comprobante_movimiento_pdf', args=[mov.ID_Movimiento_stock])
                    if emitir_comprobantes else ''
                ),
            })

    return {
        'usuario': {
            'nombre': usuario.Nombre_usuario,
            'perfil': usuario.ID_Perfil.Nombre_perfil,
        },
        'permisos': {
            'productos': ver_productos,
            'movimientos': ver_movimientos,
            'lotes': ver_lotes,
            'alertas': ver_alertas,
        },
        'urls': {
            'productos': reverse('gestion_productos'),
            'movimientos': reverse('gestion_movimientos_stock'),
            'lotes': reverse('registrar_ingreso_lote'),
            'alertas': reverse('historial_alertas'),
        },
        'metricas': metricas,
        'grafico': grafico,
        'stock_bajo': stock_bajo,
        'por_vencer': por_vencer,
        'movimientos': movimientos,
    }


def panel_principal(request):
    """Panel principal. La pantalla la dibuja un componente React
    (static/inventario/react/panel_principal.jsx) con estos datos."""

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    return render(
        request,
        'inventario/panel_principal.html',
        {
            'usuario': usuario,
            'datos_panel': _datos_panel(usuario),
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

    # Un proveedor solo se puede eliminar si nunca se usó:
    # sin remitos y sin productos asociados. Si no, se da de baja.
    con_remitos = set(
        Remitos.objects.values_list('ID_Proveedor', flat=True)
    )

    con_productos = set(
        Productos.objects.filter(
            proveedores__isnull=False
        ).values_list('proveedores', flat=True)
    )

    proveedores = list(proveedores)

    for proveedor in proveedores:
        proveedor.eliminable = (
            proveedor.pk not in con_remitos
            and proveedor.pk not in con_productos
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

    usuario = usuario_con_acceso(request, 'proveedores', gestionar=True)

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

    proveedor = form.save()
    registrar_auditoria(usuario, 'Proveedores', proveedor, 'CREACION', {}, snapshot(proveedor))

    messages.success(
        request,
        'Proveedor registrado correctamente.'
    )

    return redirect('gestion_proveedores')


def editar_proveedor(request, pk):

    usuario = usuario_con_acceso(request, 'proveedores', gestionar=True)

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

    antes = snapshot(proveedor)

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


@require_POST
def eliminar_proveedor(request, pk):
    """Elimina un proveedor solo si nunca se usó.
    Si tiene remitos o productos, se debe dar de baja."""

    usuario = usuario_con_acceso(request, 'proveedores', gestionar=True)

    if not usuario:
        return redirect('panel_principal')

    proveedor = get_object_or_404(Proveedores, ID_Proveedor=pk)
    nombre = proveedor.nombre_proveedor

    if Remitos.objects.filter(ID_Proveedor=proveedor).exists():
        messages.error(
            request,
            f'No se puede eliminar el proveedor "{nombre}" porque tiene '
            'remitos registrados. Podés darlo de baja.'
        )
        return redirect('gestion_proveedores')

    if Productos.objects.filter(proveedores=proveedor).exists():
        messages.error(
            request,
            f'No se puede eliminar el proveedor "{nombre}" porque tiene '
            'productos asociados. Podés darlo de baja.'
        )
        return redirect('gestion_proveedores')

    try:
        with transaction.atomic():
            registrar_auditoria(
                usuario, 'Proveedores', proveedor, 'ELIMINACION',
                snapshot(proveedor), {}
            )
            proveedor.delete()

    except (ProtectedError, RestrictedError, IntegrityError):
        messages.error(
            request,
            f'No se puede eliminar el proveedor "{nombre}" porque tiene '
            'registros asociados. Podés darlo de baja.'
        )
        return redirect('gestion_proveedores')

    messages.success(request, f'El proveedor "{nombre}" fue eliminado.')

    return redirect('gestion_proveedores')


def cambiar_estado_proveedor(request, pk):
    """Da de baja o activa un proveedor.

    La pantalla lo llama con JavaScript (fetch): en ese caso responde
    JSON y no guarda un mensaje, porque si no aparecería repetido
    la próxima vez que se cargue la página.
    """

    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def responder_error(texto, status):
        if es_ajax:
            return JsonResponse({'ok': False, 'error': texto}, status=status)

        messages.error(request, texto)
        return redirect('gestion_proveedores')

    usuario = usuario_con_acceso(request, 'proveedores', gestionar=True)

    if not usuario:
        if es_ajax:
            return JsonResponse(
                {'ok': False,
                 'error': 'No tenés permiso para cambiar el estado de proveedores.'},
                status=403
            )
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_proveedores')

    proveedor = Proveedores.objects.filter(ID_Proveedor=pk).first()

    if not proveedor:
        return responder_error('El proveedor seleccionado no existe.', 404)

    estado_solicitado = request.POST.get(
        'estado',
        ''
    ).strip().lower()

    if estado_solicitado not in ('activo', 'inactivo'):
        return responder_error('El estado solicitado no es válido.', 400)

    antes = snapshot(proveedor)

    if estado_solicitado == 'inactivo':
        proveedor.estado_proveedor = False
        mensaje = (
            f'El proveedor "{proveedor.nombre_proveedor}" '
            'fue dado de baja correctamente.'
        )
    else:
        proveedor.estado_proveedor = True
        mensaje = (
            f'El proveedor "{proveedor.nombre_proveedor}" '
            'fue activado correctamente.'
        )

    proveedor.save(
        update_fields=['estado_proveedor']
    )

    registrar_auditoria(
        usuario,
        'Proveedores',
        proveedor,
        'ACTIVACION' if proveedor.estado_proveedor else 'BAJA',
        antes,
        snapshot(proveedor)
    )

    if es_ajax:
        return JsonResponse({
            'ok': True,
            'mensaje': mensaje,
            'activo': proveedor.estado_proveedor,
        })

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

    tipo = TiposProductos.objects.create(
        Nombre_tipo_producto=nombre,
        Estado_tipo_producto=True
    )

    registrar_auditoria(usuario, 'Tipos de productos', tipo, 'CREACION', {}, snapshot(tipo))

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

    despues = snapshot(tipo)

    registrar_auditoria(
        usuario,
        'Tipos de productos',
        tipo,
        accion_por_estado(antes, despues, 'Estado_tipo_producto', True),
        antes,
        despues
    )

    messages.success(
        request,
        f'Tipo de producto actualizado correctamente. '
        f'Estado: {"Activo" if tipo.Estado_tipo_producto else "Inactivo"}.'
    )

    return redirect('gestion_tipos_productos')


# ============================================================
# ELIMINAR TIPO DE PRODUCTO
# Solo se elimina si no tiene productos asociados.
# Si tiene subtipos (sin productos), se eliminan junto con él.
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

    if request.method != 'POST':
        return redirect('gestion_tipos_productos')

    nombre = ''
    cantidad_subtipos = 0

    try:
        with transaction.atomic():

            tipo = get_object_or_404(
                TiposProductos.objects.select_for_update(),
                ID_Tipo_producto=pk
            )

            nombre = tipo.Nombre_tipo_producto

            # Regla principal: nada que tenga productos se elimina.
            cantidad_productos = Productos.objects.filter(
                ID_Tipo_producto=tipo
            ).count()

            if cantidad_productos > 0:
                messages.error(
                    request,
                    f'No se puede eliminar el tipo "{nombre}" porque '
                    f'tiene {cantidad_productos} producto(s) asociado(s).'
                )
                return redirect('gestion_tipos_productos')

            subtipos = list(
                Subtipos.objects.select_for_update().filter(
                    ID_Tipo_producto=tipo
                )
            )

            # Control extra: ningún subtipo del tipo puede tener productos.
            if Productos.objects.filter(ID_Subtipo__in=subtipos).exists():
                messages.error(
                    request,
                    f'No se puede eliminar el tipo "{nombre}" porque '
                    'alguno de sus subtipos tiene productos asociados.'
                )
                return redirect('gestion_tipos_productos')

            cantidad_subtipos = len(subtipos)

            # Auditoría: cada subtipo eliminado queda registrado.
            for subtipo in subtipos:
                registrar_auditoria(
                    usuario, 'Subtipos', subtipo, 'ELIMINACION',
                    dict(snapshot(subtipo), Motivo=f'Se eliminó el tipo "{nombre}"'),
                    {}
                )
                subtipo.delete()

            registrar_auditoria(
                usuario, 'Tipos de productos', tipo, 'ELIMINACION',
                dict(
                    snapshot(tipo),
                    Subtipos_eliminados=', '.join(
                        sorted(s.Nombre_subtipo for s in subtipos)
                    ) or 'Ninguno'
                ),
                {}
            )
            tipo.delete()

    except (ProtectedError, RestrictedError):
        messages.error(
            request,
            f'No se puede eliminar el tipo "{nombre}" porque '
            'tiene otros registros relacionados.'
        )
        return redirect('gestion_tipos_productos')

    mensaje = f'El tipo "{nombre}" fue eliminado correctamente.'

    if cantidad_subtipos:
        mensaje += f' También se eliminaron sus {cantidad_subtipos} subtipo(s).'

    messages.success(request, mensaje)

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

    # Cuántos productos usa cada subtipo:
    # solo se puede eliminar si no tiene ninguno.
    productos_por_subtipo = {}

    for subtipo_id in Productos.objects.filter(
        ID_Subtipo__isnull=False
    ).values_list('ID_Subtipo', flat=True):
        productos_por_subtipo[subtipo_id] = (
            productos_por_subtipo.get(subtipo_id, 0) + 1
        )

    subtipos = list(subtipos)

    for subtipo in subtipos:
        subtipo.cantidad_productos = productos_por_subtipo.get(
            subtipo.ID_Subtipo, 0
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

    usuario = usuario_con_acceso(request, 'subtipos', gestionar=True)

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

        subtipo = Subtipos.objects.create(**datos_subtipo)
        registrar_auditoria(usuario, 'Subtipos', subtipo, 'CREACION', {}, snapshot(subtipo))

        messages.success(
            request,
            'Subtipo creado correctamente.'
        )

    return redirect('gestion_subtipos')


def editar_subtipo(request, pk):

    usuario = usuario_con_acceso(request, 'subtipos', gestionar=True)

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

        registrar_auditoria(
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

    usuario = usuario_con_acceso(request, 'subtipos', gestionar=True)

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
            registrar_auditoria(usuario, 'Subtipos', subtipo, 'ELIMINACION', snapshot(subtipo), {})
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

    # No existe "Consultar usuarios": ver la lista requiere "Gestionar usuarios".
    usuario = usuario_con_acceso(request, 'usuarios', gestionar=True)

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

    # Solo perfiles activos: crear_usuario rechaza los inactivos.
    perfiles = Perfiles.objects.filter(
        Estado_perfil=True
    ).order_by('Nombre_perfil')

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


# ============================================================
# REGLAS DE LA CONTRASEÑA
# Se usan al crear un usuario, al restablecer, al cambiar
# y al recuperar la contraseña por correo.
# ============================================================

def validar_contrasena(contrasena, usuario=''):
    """Devuelve un mensaje de error, o None si la contraseña es válida."""

    if len(contrasena) < 8:
        return 'La contraseña debe tener al menos 8 caracteres.'
    if ' ' in contrasena:
        return 'La contraseña no puede tener espacios.'
    if not re.search(r'[A-Z]', contrasena):
        return 'La contraseña debe tener al menos una mayúscula.'
    if not re.search(r'[a-z]', contrasena):
        return 'La contraseña debe tener al menos una minúscula.'
    if not re.search(r'\d', contrasena):
        return 'La contraseña debe tener al menos un número.'
    if usuario and usuario.lower() in contrasena.lower():
        return 'La contraseña no puede contener el nombre de usuario.'
    return None


def crear_usuario(request):

    usuario_admin = usuario_con_acceso(request, 'usuarios', gestionar=True)

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

        # Reglas de la contraseña (se valida acá porque necesita
        # el nombre de usuario generado).
        error = validar_contrasena(contrasena, usuario_generado)

        if error:
            messages.error(request, error)
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

        registrar_auditoria(usuario_admin, 'Usuarios', nuevo, 'CREACION', {}, snapshot(nuevo))
        registrar_asignacion_perfil(usuario_admin, nuevo, None, perfil)


        messages.success(
            request,
            f'El usuario {nuevo.Usuario} '
            'ha sido registrado correctamente. '
            'Deberá cambiar su contraseña '
            'en el próximo inicio de sesión.'
        )

    return redirect('gestion_usuarios')


def editar_usuario(request, pk):
    """Modifica el email de un usuario desde el modal de usuarios.html."""

    usuario_admin = usuario_con_acceso(request, 'usuarios', gestionar=True)

    if not usuario_admin:
        return redirect('panel_principal')

    # La edición se hace desde el modal: no hay pantalla propia.
    if request.method != 'POST':
        return redirect('gestion_usuarios')

    usuario_editado = get_object_or_404(
        Usuarios,
        ID_Usuario=pk
    )

    antes = snapshot(usuario_editado)

    nuevo_email = request.POST.get(
        'Email_usuario',
        ''
    ).strip()

    if not nuevo_email:
        messages.error(
            request,
            'El correo electrónico es obligatorio.'
        )
        return redirect('gestion_usuarios')

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
        return redirect('gestion_usuarios')

    usuario_editado.Email_usuario = nuevo_email
    usuario_editado.save()

    registrar_auditoria(
        usuario_admin,
        'Usuarios',
        usuario_editado,
        'MODIFICACION',
        antes,
        snapshot(usuario_editado)
    )

    messages.success(
        request,
        f'El usuario {usuario_editado.Usuario} '
        'ha sido modificado correctamente.'
    )

    return redirect('gestion_usuarios')


def dar_baja_usuario(request, pk):

    usuario_admin = usuario_con_acceso(request, 'usuarios', gestionar=True)

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

        registrar_auditoria(usuario_admin, 'Usuarios', usuario, 'BAJA', antes, snapshot(usuario))
        messages.success(
            request,
            'Usuario dado de baja correctamente.'
        )

    return redirect('gestion_usuarios')


def activar_usuario(request, id):

    usuario_admin = usuario_con_acceso(request, 'usuarios', gestionar=True)

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

        registrar_auditoria(usuario_admin, 'Usuarios', usuario, 'ACTIVACION', antes, snapshot(usuario))
        messages.success(
            request,
            f'El usuario {usuario.Usuario} '
            'fue activado correctamente.'
        )

    return redirect('gestion_usuarios')


@require_POST
def enviar_enlace_recuperacion(request, pk):

    usuario_admin = usuario_con_acceso(request, 'usuarios', gestionar=True)

    if not usuario_admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(
        Usuarios,
        ID_Usuario=pk
    )

    if not usuario_habilitado(usuario):
        messages.error(
            request,
            f'El usuario {usuario.Usuario} está dado de baja. '
            'Actívelo antes de enviarle el enlace.'
        )
        return redirect('gestion_usuarios')

    if not usuario.Email_usuario:
        messages.error(
            request,
            f'El usuario {usuario.Usuario} no tiene un correo registrado.'
        )
        return redirect('gestion_usuarios')

    enviar_correo_recuperacion(usuario)

    # La contraseña no cambia: solo se registra a quién y a dónde se envió el enlace.
    despues = {
        'Usuario': usuario.Usuario,
        'Correo': usuario.Email_usuario,
        'Vigencia del enlace': '1 hora',
    }
    registrar_auditoria(usuario_admin, 'Usuarios', usuario, 'ENVIO_RECUPERACION', {}, despues)

    messages.success(
        request,
        f'Se envió el enlace de recuperación a {usuario.Email_usuario}. '
        'El enlace vence en 1 hora.'
    )

    return redirect('gestion_usuarios')


def restablecer_contrasena(request, pk):

    usuario_admin = usuario_con_acceso(request, 'usuarios', gestionar=True)

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

    error = validar_contrasena(nueva_contrasena, usuario.Usuario)

    if error:
        messages.error(request, error)
        return redirect('gestion_usuarios')

    antes = snapshot(usuario)
    antes['Contrasena'] = 'anterior'

    usuario.Contrasena = make_password(nueva_contrasena)
    usuario.Cambiar_contrasena = True
    usuario.save()

    despues = snapshot(usuario)
    despues['Contrasena'] = 'restablecida'
    registrar_auditoria(usuario_admin, 'Usuarios', usuario, 'RESET_CONTRASENA', antes, despues)
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

        error = validar_contrasena(nueva_contrasena, usuario.Usuario)

        if error:
            messages.error(request, error)

            return render(
                request,
                'inventario/cambiar_contrasena.html',
                {'usuario': usuario}
            )

        # cambiar_contrasena (la propia):
        antes = snapshot(usuario)
        antes['Contrasena'] = 'anterior'
        usuario.Contrasena = make_password(nueva_contrasena)
        usuario.Cambiar_contrasena = False
        usuario.save()
        despues = snapshot(usuario)
        despues['Contrasena'] = 'cambiada por el usuario'
        registrar_auditoria(usuario, 'Usuarios', usuario, 'MODIFICACION', antes, despues)

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
# SINCRONIZACIÓN DE PERMISOS
# El catálogo de permisos vive en el código (permissions.py).
# Esta función crea en la base los que todavía no existen,
# así todos aparecen en "Perfiles de acceso" y se pueden asignar.
# Los permisos NO se crean ni se eliminan desde la interfaz.
# ============================================================

def sincronizar_permisos():
    """Crea en la base los permisos del catálogo que todavía no existen."""

    existentes = {
        nombre.strip().lower()
        for nombre in Permisos.objects.values_list(
            'Nombre_permiso', flat=True
        )
    }

    for nombre, descripcion, grupo in catalogo_plano():
        if nombre.strip().lower() not in existentes:
            Permisos.objects.create(Nombre_permiso=nombre.strip())
            existentes.add(nombre.strip().lower())


def _permisos_agrupados():
    """Permisos del catálogo agrupados por módulo, con su ID en la base.

    La descripción sale del catálogo, igual que en "Permisos del sistema",
    así el texto es el mismo en las dos pantallas.
    """

    en_bd = {
        p.Nombre_permiso.strip().lower(): p
        for p in Permisos.objects.all()
    }

    grupos = {}

    for nombre, descripcion, grupo in catalogo_plano():
        permiso = en_bd.get(nombre.strip().lower())

        if not permiso:
            continue

        grupos.setdefault(grupo, []).append({
            'id': permiso.ID_Permiso,
            'nombre': nombre,
            'descripcion': descripcion,
        })

    return grupos


# ============================================================
# GESTIÓN DE PERFILES
# ============================================================

def _permisos_de(perfil):
    return set(
        PerfilesXPermisos.objects.filter(ID_Perfil=perfil)
        .values_list('ID_Permiso__Nombre_permiso', flat=True)
    )

def gestion_perfiles(request):

    usuario = usuario_con_acceso(request, 'perfiles')

    if not usuario:
        return redirect('panel_principal')

    sincronizar_permisos()

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

    return render(
        request,
        'inventario/perfiles.html',
        {
            'perfiles': perfiles,
            'grupos_permisos': _permisos_agrupados().items(),
            'busqueda': busqueda,
            'usuario': usuario,
            'perfiles_admin': PERFILES_ADMIN,
        }
    )


def crear_perfil(request):

    usuario = usuario_con_acceso(request, 'perfiles', gestionar=True)

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
            registrar_auditoria(usuario, 'Perfiles', perfil, 'CREACION', {}, snapshot(perfil))
            registrar_asignacion_permisos(usuario, perfil, set(), _permisos_de(perfil))

        messages.success(
            request,
            'Perfil creado correctamente.'
        )

    return redirect('gestion_perfiles')


def editar_perfil(request, pk):

    usuario = usuario_con_acceso(request, 'perfiles', gestionar=True)

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

        antes = snapshot(perfil)
        permisos_antes = _permisos_de(perfil)

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

            registrar_auditoria(usuario, 'Perfiles', perfil, 'MODIFICACION', antes, snapshot(perfil))
            registrar_asignacion_permisos(usuario, perfil, permisos_antes, _permisos_de(perfil))

        messages.success(
            request,
            'Perfil actualizado correctamente.'
        )

    return redirect('gestion_perfiles')


# ============================================================
# CAMBIAR ESTADO DEL PERFIL
# ============================================================

def cambiar_estado_perfil(request, id):

    usuario = usuario_con_acceso(request, 'perfiles', gestionar=True)

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

        registrar_auditoria(usuario, 'Perfiles', perfil, 'BAJA', antes, snapshot(perfil))
        messages.success(
            request,
            f'El perfil "{perfil.Nombre_perfil}" '
            'fue dado de baja correctamente.'
        )

    else:
        # Si está inactivo, se intenta activar.
        perfil.Estado_perfil = True
        perfil.save(update_fields=['Estado_perfil'])

        registrar_auditoria(usuario, 'Perfiles', perfil, 'ACTIVACION', antes, snapshot(perfil))
        messages.success(
            request,
            f'El perfil "{perfil.Nombre_perfil}" '
            'fue activado correctamente.'
        )

    return redirect('gestion_perfiles')
# ============================================================
# GESTIÓN DE PERMISOS (solo lectura)
# ============================================================

# Ícono de cada módulo en las tarjetas de "Permisos del sistema".
# Son los mismos íconos del menú lateral (_sidebar.html).
ICONOS_MODULO = (
    ('usuario', 'i-users'),
    ('subtipo', 'i-tags'),
    ('tipo', 'i-layers'),
    ('producto', 'i-package'),
    ('proveedor', 'i-truck'),
    ('remito', 'i-inbox'),
    ('lote', 'i-package'),
    ('movimiento', 'i-swap'),
    ('alerta', 'i-bell'),
    ('reporte', 'i-chart'),
    ('seguridad', 'i-shield'),
)


def _icono_modulo(nombre):
    nombre = nombre.lower()

    for palabra, icono in ICONOS_MODULO:
        if palabra in nombre:
            return icono

    return 'i-key'


def gestion_permisos(request):

    usuario = usuario_con_acceso(request, 'permisos')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para consultar los permisos del sistema.'
        )
        return redirect('panel_principal')

    sincronizar_permisos()

    busqueda = request.GET.get('q', '').strip()
    filtro = busqueda.lower()

    en_bd = {
        p.Nombre_permiso.strip().lower(): p
        for p in Permisos.objects.prefetch_related('perfiles')
    }

    grupos = {}
    total = 0

    for nombre, descripcion, grupo in catalogo_plano():
        if filtro and filtro not in nombre.lower() and filtro not in descripcion.lower():
            continue

        permiso = en_bd.get(nombre.strip().lower())

        grupos.setdefault(grupo, []).append({
            'nombre': nombre,
            'descripcion': descripcion,
            'sincronizado': permiso is not None,
            'perfiles': (
                sorted(permiso.perfiles.all(), key=lambda p: p.Nombre_perfil.lower())
                if permiso else []
            ),
        })
        total += 1

    # Una tarjeta por módulo: ícono, permisos y cuántos perfiles
    # distintos tienen al menos uno de esos permisos.
    modulos = []

    for nombre_grupo, permisos_grupo in grupos.items():
        perfiles_distintos = {
            perfil.ID_Perfil
            for permiso in permisos_grupo
            for perfil in permiso['perfiles']
        }

        modulos.append({
            'nombre': nombre_grupo,
            'icono': _icono_modulo(nombre_grupo),
            'permisos': permisos_grupo,
            'cantidad_perfiles': len(perfiles_distintos),
        })

    return render(
        request,
        'inventario/permisos.html',
        {
            'modulos': modulos,
            'total': total,
            'total_modulos': len(modulos),
            'busqueda': busqueda,
            'usuario': usuario,
            'activo': 'permisos',
        }
    )



# ============================================================
# MIS PERMISOS
# ============================================================

def mis_permisos(request):
    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    es_admin = usuario.ID_Perfil.Nombre_perfil in PERFILES_ADMIN
    asignados = permisos_asignados(usuario)
    catalogo = catalogo_plano()

    grupos = {}

    for nombre, descripcion, grupo in catalogo:
        if es_admin or nombre.strip().lower() in asignados:
            grupos.setdefault(grupo, []).append({
                'nombre': nombre,
                'descripcion': descripcion,
            })

    modulos = [
        {'nombre': g, 'icono': _icono_modulo(g), 'permisos': p}
        for g, p in grupos.items()
    ]

    total = sum(len(m['permisos']) for m in modulos)

    return render(
        request,
        'inventario/mis_permisos.html',
        {
            'usuario': usuario,
            'modulos': modulos,
            'total': total,
            'total_catalogo': len(catalogo),
            'porcentaje': round(total * 100 / len(catalogo)) if catalogo else 0,
            'es_admin': es_admin,
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

    nombre = request.POST.get('Nombre_producto', '').strip()
    descripcion = request.POST.get(
        'Descripcion_producto', ''
    ).strip()

    precio_input = request.POST.get('Precio', '').strip()
    cantidad_input = request.POST.get(
        'Cantidad_presentacion', ''
    ).strip()

    unidades_input = request.POST.get(
        'Unidades_por_presentacion', ''
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
    # VALIDAR UNIDADES POR PRESENTACIÓN
    # --------------------------------------------------------

    try:
        unidades_por_presentacion = int(unidades_input or 1)
    except (ValueError, TypeError):
        return None, 'Las unidades por presentación no son válidas.'

    if unidades_por_presentacion < 1:
        return None, 'Las unidades por presentación deben ser al menos 1.'

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
    # VALIDAR PROVEEDORES QUE SUMINISTRAN EL PRODUCTO
    # --------------------------------------------------------

    ids_proveedores = {
        i.strip()
        for i in request.POST.getlist('proveedores')
        if i.strip().isdigit()
    }

    proveedores_producto = list(
        Proveedores.objects.filter(
            ID_Proveedor__in=ids_proveedores,
            estado_proveedor=True
        )
    )

    if not proveedores_producto:
        return None, 'Seleccioná al menos un proveedor que suministre el producto.'

    if len(proveedores_producto) != len(ids_proveedores):
        return None, 'Alguno de los proveedores seleccionados no existe o está inactivo.'

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
        'nombre': nombre,
        'descripcion': descripcion or None,
        'precio': precio,
        'cantidad_presentacion': cantidad_presentacion,
        'unidades_por_presentacion': unidades_por_presentacion,
        'proveedores': proveedores_producto,
        'unidad_medida': unidad_medida or None,
        'estado_producto': estado_producto,
    }

    return datos, None


def _producto_duplicado(nombre, cantidad_presentacion, unidad_medida,
                        unidades, excluir_pk=None):
    """Comprueba si existe otro producto con el mismo nombre y la misma
    presentación (cantidad y unidad de medida).

    Las unidades por caja ya no son del producto: se cargan en cada lote.

    El sistema no usa marca: un mismo producto puede venir de varios
    proveedores, y el proveedor queda registrado en cada lote.
    """

    productos = Productos.objects.filter(
        Nombre_producto__iexact=nombre,
        Cantidad_presentacion=cantidad_presentacion,
    )

    if unidad_medida:
        productos = productos.filter(
            Unidad_medida_producto__iexact=unidad_medida
        )
    else:
        productos = productos.filter(
            Q(Unidad_medida_producto__isnull=True) |
            Q(Unidad_medida_producto='')
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
        messages.error(
            request,
            'No tenés permiso para consultar productos.'
        )
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()
    tipo_id = request.GET.get('tipo', '').strip()


    productos = Productos.objects.select_related(
        'ID_Tipo_producto',
        'ID_Subtipo',
        'stock'
    ).prefetch_related(
        'proveedores',
        Prefetch(
            'lotes',
            queryset=Lotes.objects.select_related(
                'ID_Remito',
                'ID_Remito__ID_Proveedor'
            ).order_by('Fecha_vencimiento', 'Numero_lote'),
            to_attr='lotes_ordenados'
        )
    ).annotate(
        # distinct: la búsqueda por proveedor agrega un JOIN que
        # sin esto multiplicaría la cantidad de lotes.
        num_lotes=Count('lotes', distinct=True)
    )

    # BÚSQUEDA
    if busqueda:
        productos = productos.filter(
            Q(Nombre_producto__icontains=busqueda) |
            Q(Descripcion_producto__icontains=busqueda) |
            Q(proveedores__nombre_proveedor__icontains=busqueda) |
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
    puede_egresar = puede(usuario, 'egresos', gestionar=True)

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
            'proveedores_activos': Proveedores.objects.filter(
                estado_proveedor=True
            ).order_by('nombre_proveedor'),
            'puede_egresar': puede_egresar,
            'datos_egreso': _datos_egreso() if puede_egresar else [],
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
        datos['cantidad_presentacion'],
        datos['unidad_medida'],
        datos['unidades_por_presentacion']
    ):
        messages.error(
            request,
            'Ya existe un producto con ese nombre y esa presentación.'
        )
        return redirect('gestion_productos')

    with transaction.atomic():

        producto = Productos.objects.create(
            ID_Tipo_producto=datos['tipo'],
            ID_Subtipo=datos['subtipo'],
            Nombre_producto=datos['nombre'],
            Descripcion_producto=datos['descripcion'],
            Precio=datos['precio'],
            Cantidad_presentacion=datos['cantidad_presentacion'],
            Unidades_por_presentacion=datos['unidades_por_presentacion'],
            Unidad_medida_producto=datos['unidad_medida'],
            Estado_producto=datos['estado_producto'],
        )

        producto.proveedores.set(datos['proveedores'])

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
        datos['cantidad_presentacion'],
        datos['unidad_medida'],
        datos['unidades_por_presentacion'],
        excluir_pk=pk
    ):
        messages.error(
            request,
            'Ya existe otro producto con ese nombre y esa presentación.'
        )
        return redirect('gestion_productos')

    with transaction.atomic():

        producto.ID_Tipo_producto = datos['tipo']
        producto.ID_Subtipo = datos['subtipo']
        producto.Nombre_producto = datos['nombre']
        producto.Descripcion_producto = datos['descripcion']
        producto.Precio = datos['precio']
        producto.Cantidad_presentacion = datos['cantidad_presentacion']
        producto.Unidades_por_presentacion = datos['unidades_por_presentacion']
        producto.Unidad_medida_producto = datos['unidad_medida']
        producto.Estado_producto = datos['estado_producto']


        producto.save()
        producto.proveedores.set(datos['proveedores'])

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

            if producto.lotes.exists():
                revisar_stock(stock, usuario)

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
            accion_por_estado(antes, despues, 'Estado_producto', 'Activo'),
            antes,
            despues
        )

    messages.success(
        request,
        'Producto actualizado correctamente.'
    )

    return redirect('gestion_productos')


def eliminar_producto(request, pk):
    """Elimina un producto únicamente si no tiene lotes ni stock."""

    usuario = usuario_con_acceso(request, 'productos', gestionar=True)

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

    # No permitir eliminar productos con stock.
    stock = Stock.objects.filter(ID_Producto=producto).first()

    if stock and stock.Cantidad_stock > 0:
        messages.error(
            request,
            f'No se puede eliminar el producto "{nombre}" porque tiene '
            f'{stock.Cantidad_stock} unidades en stock. Podés cambiar su estado a Inactivo.'
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

    except (ProtectedError, RestrictedError, IntegrityError):
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
    proveedor_filtro = request.GET.get('proveedor', '').strip()

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

    if proveedor_filtro.isdigit():
        lotes = lotes.filter(ID_Remito__ID_Proveedor_id=proveedor_filtro)
    else:
        proveedor_filtro = ''

    hoy = timezone.localdate()


    # Proveedores que tienen al menos un remito (los únicos con lotes).
    proveedores = Proveedores.objects.filter(
        remitos__isnull=False
    ).distinct().order_by('nombre_proveedor')

    return render(
        request,
        'inventario/registrar_ingreso_lote.html',
        {
            'usuario': usuario,
            'lotes': lotes,
            'proveedores': proveedores,
            'busqueda': busqueda,
            'proveedor_filtro': proveedor_filtro,
            'hoy': hoy,
            'limite': hoy + timedelta(days=DIAS_AVISO_VENCIMIENTO),
        }
    )

@transaction.atomic
def baja_lote_vencido(request, id_lote):

    usuario = usuario_con_acceso(request, 'egresos', gestionar=True)

    if not usuario:
        messages.error(request, "No tenés permisos para realizar esta operación.")
        return redirect('panel_principal')

    # La operación debe realizarse mediante POST
    if request.method != 'POST':
        return redirect('registrar_ingreso_lote')

    # Buscar y bloquear el lote
    lote = get_object_or_404(
        Lotes.objects.select_for_update(),
        ID_Lote=id_lote
    )

    # Verificar fecha de vencimiento
    if not lote.Fecha_vencimiento:
        messages.error(request, "El lote no tiene fecha de vencimiento registrada.")
        return redirect('registrar_ingreso_lote')

    if lote.Fecha_vencimiento >= timezone.localdate():
        messages.error(request, "El lote todavía no se encuentra vencido.")
        return redirect('registrar_ingreso_lote')

    # Verificar cantidad disponible
    cantidad = lote.Cantidad_actual

    if cantidad <= 0:
        messages.warning(request, "El lote no tiene unidades disponibles.")
        return redirect('registrar_ingreso_lote')

    # Buscar y bloquear el stock del producto
    stock = Stock.objects.select_for_update().get(
        ID_Producto=lote.ID_Producto
    )

    if stock.Cantidad_stock < cantidad:
        messages.error(
            request,
            "La cantidad del lote supera el stock disponible del producto."
        )
        return redirect('registrar_ingreso_lote')

    # Guardar cantidades anteriores para la auditoría
    lote_antes = lote.Cantidad_actual
    stock_antes = stock.Cantidad_stock
    producto = lote.ID_Producto

    # Buscar el tipo de movimiento
    tipo_movimiento = get_object_or_404(
        TiposMovimientos,
        Nombre_tipo_movimiento__iexact='Salida por vencimiento de producto'
    )

    # Descontar cantidades
    stock.Cantidad_stock -= cantidad
    stock.save(update_fields=['Cantidad_stock'])

    lote.Cantidad_actual = 0
    lote.save(update_fields=['Cantidad_actual'])

    detalle = f"Salida por vencimiento del lote {lote.Numero_lote}"

    # Registrar movimiento de stock
    movimiento = MovimientosStock.objects.create(
        ID_Usuario=usuario,
        ID_Tipo_movimiento=tipo_movimiento,
        ID_Lote=lote,
        Cantidad_movimiento_stock=cantidad,
        Observaciones=detalle
    )

    # Registrar auditoría como egreso por vencimiento
    registrar_auditoria(
        usuario,
        'Movimientos de Stock',
        movimiento,
        'EGRESO_VENCIMIENTO',
        {},
        {
            'Tipo_movimiento': 'Salida por vencimiento de producto',
            'ID_Producto': producto.pk,
            'Lote': lote.Numero_lote,
            'Fecha_vencimiento': lote.Fecha_vencimiento.strftime('%d/%m/%Y'),
            'Cantidad': cantidad,
            'Lote_antes': lote_antes,
            'Lote_despues': lote.Cantidad_actual,
            'Stock_antes': stock_antes,
            'Stock_despues': stock.Cantidad_stock,
            'Observaciones': detalle[:255],
        }
    )

    messages.success(
        request,
        f"Se registró la baja por vencimiento del lote {lote.Numero_lote}."
    )

    return redirect('registrar_ingreso_lote')




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

    tipos_visibles = [
        'Entrada de lote',
        'Salida por vencimiento de producto',
        TIPO_EGRESO,
        TIPO_ANULACION_REMITO,
        TIPO_ANULACION_EGRESO,
    ]

    # Asegura que los tipos existan en la base de datos.
    for nombre_tipo in tipos_visibles:
        TiposMovimientos.objects.get_or_create(
            Nombre_tipo_movimiento=nombre_tipo
        )

    movimientos = MovimientosStock.objects.select_related(
        'ID_Usuario',
        'ID_Usuario_anulacion',
        'ID_Tipo_movimiento',
        'ID_Lote',
        'ID_Lote__ID_Producto',
        'ID_Lote__ID_Remito',
        'ID_Lote__ID_Remito__ID_Proveedor'
    ).filter(
        ID_Tipo_movimiento__Nombre_tipo_movimiento__in=tipos_visibles
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

    todos_tipos = TiposMovimientos.objects.filter(
        Nombre_tipo_movimiento__in=tipos_visibles
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
            'puede_anular': puede_accion(usuario, 'anular_egresos'),
        }
    )


# ============================================================
# ALERTAS
# La lógica (stock mínimo, vencimientos y correos) está en alertas.py.
# generar_alertas_vencimiento se importa de ahí con ese nombre.
# ============================================================

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

    if tipo_alerta == TIPO_STOCK:
        alertas_bd = alertas_bd.filter(
            Tipo_alerta__in=TIPOS_STOCK
        )
    elif tipo_alerta:
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
            mensaje = mensaje_visible(mensaje)

        alertas.append({
            'id': alerta.ID_Historial_alerta,
            'tipo': (
                TIPO_STOCK if alerta.Tipo_alerta in TIPOS_STOCK
                else alerta.Tipo_alerta
            ),
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
    """Marca una alerta como atendida.

    Desde el historial vuelve a la pantalla; desde la bandeja de
    notificaciones del topbar (JavaScript) responde JSON.
    """

    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    usuario = usuario_con_accion(request, 'atender_alertas')

    if not usuario:
        if es_ajax:
            return JsonResponse(
                {'ok': False, 'error': 'No tenés permiso para atender alertas.'},
                status=403
            )
        return redirect('panel_principal')

    alerta = get_object_or_404(
        Alertas,
        ID_Historial_alerta=id_alerta
    )

    if not alerta.Atendida:
        antes = snapshot(alerta)
        alerta.Atendida = True
        alerta.ID_Usuario = usuario
        alerta.Fecha_hora_atencion = timezone.now()

        alerta.save(update_fields=[
            'Atendida',
            'ID_Usuario',
            'Fecha_hora_atencion',
        ])
        registrar_auditoria(
            usuario,
            'Historial de alertas',
            alerta,
            'ATENCION_ALERTA',
            antes,
            snapshot(alerta)
        )

    if es_ajax:
        return JsonResponse({
            'ok': True,
            'pendientes': Alertas.objects.filter(Atendida=False).count(),
        })

    return redirect('historial_alertas')


# ============================================================
# BANDEJA DE NOTIFICACIONES (topbar)
# ============================================================

def notificaciones_alertas(request):
    """Alertas pendientes para la bandeja del topbar (JSON)."""

    usuario = usuario_con_acceso(request, 'alertas')

    if not usuario:
        return JsonResponse(
            {'error': 'No tenés permiso para ver las alertas.'},
            status=403
        )

    return JsonResponse(listar_notificaciones())


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

    if movimiento.Anulado:
        filas.append((
            'Estado:',
            'ANULADO el '
            f'{timezone.localtime(movimiento.Fecha_anulacion).strftime("%d/%m/%Y %H:%M")}'
            f'. Motivo: {movimiento.Motivo_anulacion}'
        ))

    buffer = BytesIO()

    _dibujar_comprobante(
        buffer,
        filas,
        logo_path=finders.find(LOGO_STATIC),
        generado=timezone.localtime().strftime('%d/%m/%Y %H:%M')
    )

    pdf = buffer.getvalue()
    buffer.close()

    registrar_auditoria(
        usuario, 'Movimientos de Stock', movimiento, 'DESCARGA_PDF', {},
        {
            'Documento': 'Comprobante de movimiento de stock',
            'Archivo': f'comprobante_movimiento_{id_movimiento}.pdf',
            'Tipo_movimiento': movimiento.ID_Tipo_movimiento.Nombre_tipo_movimiento,
        }
    )

    respuesta = HttpResponse(
        pdf,
        content_type='application/pdf'
    )

    respuesta['Content-Disposition'] = (
        f'inline; filename="comprobante_movimiento_{id_movimiento}.pdf"'
    )
    respuesta['Content-Length'] = len(pdf)

    return respuesta



# ============================================================
# PDF DEL REMITO CON SUS LOTES
# ============================================================

LOGO_REMITO_STATIC = 'inventario/images/logo_agroquimica.png'


def remito_pdf(request, id_remito):
    """Descarga el remito con sus lotes en PDF.

    Lo puede descargar cualquiera que pueda consultar remitos.
    """

    usuario = usuario_con_acceso(request, 'remitos')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para consultar remitos.'
        )
        return redirect('panel_principal')

    remito = get_object_or_404(
        Remitos.objects.select_related(
            'ID_Proveedor',
            'ID_Usuario_anulacion',
        ),
        ID_Remito=id_remito
    )

    lotes = list(
        Lotes.objects.filter(
            ID_Remito=remito
        ).select_related(
            'ID_Producto'
        ).order_by('ID_Lote')
    )

    # Quién registró el ingreso: el usuario del primer movimiento de entrada.
    entrada = MovimientosStock.objects.filter(
        ID_Lote__ID_Remito=remito,
        ID_Tipo_movimiento__Nombre_tipo_movimiento__iexact='Entrada de lote'
    ).select_related(
        'ID_Usuario'
    ).order_by('Fecha_hora_movimiento').first()

    registrado_por = None

    if entrada and entrada.ID_Usuario:
        registrado_por = (
            f'{entrada.ID_Usuario.Nombre_usuario} '
            f'{entrada.ID_Usuario.Apellido_usuario}'
        )

    pdf = generar_pdf_remito(
        remito,
        lotes,
        registrado_por=registrado_por,
        logo_path=finders.find(LOGO_REMITO_STATIC),
        emitido=timezone.localtime().strftime('%d/%m/%Y %H:%M'),
    )

    # Nombre del archivo sin caracteres raros: remito_R-0001-000009.pdf
    numero_archivo = re.sub(r'[^A-Za-z0-9_-]', '_', remito.Numero_remito)
    nombre_archivo = f'remito_{numero_archivo}.pdf'

    registrar_auditoria(
        usuario, 'Remitos', remito, 'DESCARGA_PDF', {},
        {
            'Documento': 'Remito con sus lotes',
            'Archivo': nombre_archivo,
            'Numero_remito': remito.Numero_remito,
            'Cantidad_lotes': len(lotes),
        }
    )

    respuesta = HttpResponse(pdf, content_type='application/pdf')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    respuesta['Content-Length'] = len(pdf)

    return respuesta



def gestion_remitos(request):
    usuario = usuario_con_acceso(
        request,
        'remitos',
        gestionar=(request.method == 'POST')
    )

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para esta operación sobre remitos.'
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
            cajas_lista = request.POST.getlist('lote_cajas')
            unidades_lista = request.POST.getlist('lote_unidades_caja')

            if not proveedor_id or not numero_remito or not fecha_texto:
                messages.error(request, 'Completá los datos del remito.')
                return redirect('gestion_remitos')

            if not (
                len(productos_ids) == len(numeros_lote)
                == len(vencimientos) == len(cajas_lista)
                == len(unidades_lista)
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

            for (
                producto_id, numero_lote, vencimiento_texto,
                cajas_texto, unidades_texto
            ) in zip(
                productos_ids, numeros_lote, vencimientos,
                cajas_lista, unidades_lista
            ):
                numero_lote = numero_lote.strip()

                if not all([
                    producto_id,
                    numero_lote,
                    vencimiento_texto,
                    cajas_texto,
                    unidades_texto
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
                    cajas = int(cajas_texto)
                    unidades_caja = int(unidades_texto)
                    fecha_vencimiento = date.fromisoformat(
                        vencimiento_texto
                    )
                except (ValueError, TypeError):
                    messages.error(
                        request,
                        'Revisá las cantidades y las fechas de los lotes.'
                    )
                    return redirect('gestion_remitos')

                if unidades_caja <= 0:
                    messages.error(
                        request,
                        'Las unidades por caja de cada lote deben ser mayor a cero.'
                    )
                    return redirect('gestion_remitos')

                if cajas <= 0:
                    messages.error(
                        request,
                        'La cantidad de cajas de cada lote debe ser mayor a cero.'
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


                # El producto debe ser suministrado por el proveedor del remito.
                if not producto.proveedores.filter(
                    pk=proveedor.pk
                ).exists():
                    messages.error(
                        request,
                        f'El producto "{producto.Nombre_producto}" no es '
                        f'suministrado por el proveedor '
                        f'"{proveedor.nombre_proveedor}".'
                    )
                    return redirect('gestion_remitos')

                # Unidades totales = cajas x unidades por caja.
                cantidad = cajas * unidades_caja

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
                    'cajas': cajas,
                    'unidades_caja': unidades_caja,
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
                    registrar_auditoria(usuario, 'Remitos', remito, 'CREACION', {},
                      dict(snapshot(remito), Cantidad_lotes=len(lotes_validados)))

                    for datos in lotes_validados:
                        lote = Lotes.objects.create(
                            ID_Remito=remito,
                            ID_Producto=datos['producto'],
                            Numero_lote=datos['numero'],
                            Cantidad_cajas=datos['cajas'],
                            Unidades_por_caja=datos['unidades_caja'],
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
                        stock_antes = stock.Cantidad_stock
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
                        registrar_auditoria(
                            usuario, 'Lotes', lote, 'INGRESO_LOTE', {},
                            dict(
                                snapshot(lote),
                                Stock_antes=stock_antes,
                                Stock_despues=stock.Cantidad_stock
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

                if remito.Estado_remito == 'Anulado':
                    messages.error(
                        request,
                        'No se puede modificar un remito anulado.'
                    )
                    return redirect('gestion_remitos')

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
            cajas_texto = request.POST.get(
                'Cantidad_cajas', ''
            ).strip()
            unidades_caja_texto = request.POST.get(
                'Unidades_por_caja', ''
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
                cajas_texto, unidades_caja_texto, cantidad_actual_texto,
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
                cajas = int(cajas_texto)
                unidades_caja = int(unidades_caja_texto)
                cantidad_actual = int(cantidad_actual_texto)
                fecha_ingreso = date.fromisoformat(fecha_ingreso_texto)
                fecha_vencimiento = date.fromisoformat(vencimiento_texto)
            except (ValueError, TypeError):
                messages.error(
                    request,
                    'Revisá las cantidades y las fechas ingresadas.'
                )
                return redirect('gestion_remitos')

            if cajas <= 0:
                messages.error(
                    request,
                    'La cantidad de cajas debe ser mayor a cero.'
                )
                return redirect('gestion_remitos')

            if unidades_caja <= 0:
                messages.error(
                    request,
                    'Las unidades por caja deben ser mayor a cero.'
                )
                return redirect('gestion_remitos')

            # Unidades totales = cajas x unidades por caja.
            cantidad_ingresada = cajas * unidades_caja

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

                    if lote.ID_Remito.Estado_remito == 'Anulado':
                        messages.error(
                            request,
                            'No se puede modificar un lote de un remito anulado.'
                        )
                        return redirect('gestion_remitos')

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

                        # Si la corrección bajó el stock, puede quedar en el mínimo.
                        revisar_stock(stock, usuario)

                        # Actualizar el movimiento de entrada existente.
                        entrada.Cantidad_movimiento_stock = cantidad_ingresada
                        entrada.save(
                            update_fields=['Cantidad_movimiento_stock']
                        )

                    lote.ID_Producto = producto
                    lote.Numero_lote = numero_lote
                    lote.Cantidad_cajas = cajas
                    lote.Unidades_por_caja = unidades_caja
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

        # ====================================================
        # ANULAR REMITO (no se elimina: cambia de estado)
        # ====================================================
        elif accion == 'anular_remito':
            remito_id = request.POST.get('ID_Remito', '').strip()
            motivo = request.POST.get('Motivo_anulacion', '').strip()

            if not puede_accion(usuario, 'anular_remitos'):
                messages.error(
                    request,
                    'No tenés permiso para anular remitos.'
                )
                return redirect('gestion_remitos')

            if len(motivo) < 10:
                messages.error(
                    request,
                    'Si anula este remito debe justificarlo '
                    '(mínimo 10 caracteres).'
                )
                return redirect('gestion_remitos')

            if len(motivo) > 200:
                messages.error(
                    request,
                    'La justificación no puede superar los 200 caracteres.'
                )
                return redirect('gestion_remitos')

            try:
                with transaction.atomic():
                    remito = Remitos.objects.select_for_update().get(
                        ID_Remito=remito_id
                    )

                    if remito.Estado_remito == 'Anulado':
                        messages.error(
                            request,
                            'El remito ya se encuentra anulado.'
                        )
                        return redirect('gestion_remitos')

                    lotes_remito = list(
                        Lotes.objects.select_for_update().select_related(
                            'ID_Producto'
                        ).filter(ID_Remito=remito)
                    )

                    # Validar todo antes de modificar nada.
                    stocks = {}

                    for lote_r in lotes_remito:
                        if lote_r.Cantidad_actual != lote_r.Cantidad_ingresada:
                            messages.error(
                                request,
                                f'No se puede anular: el lote '
                                f'"{lote_r.Numero_lote}" ya tuvo salidas.'
                            )
                            return redirect('gestion_remitos')

                        stock_r = stocks.get(lote_r.ID_Producto_id)

                        if stock_r is None:
                            stock_r = Stock.objects.select_for_update().filter(
                                ID_Producto=lote_r.ID_Producto
                            ).first()
                            stocks[lote_r.ID_Producto_id] = stock_r

                        if not stock_r:
                            messages.error(
                                request,
                                f'No se encontró el stock de '
                                f'"{lote_r.ID_Producto.Nombre_producto}".'
                            )
                            return redirect('gestion_remitos')

                    tipo_anulacion, _ = TiposMovimientos.objects.get_or_create(
                        Nombre_tipo_movimiento=TIPO_ANULACION_REMITO
                    )

                    antes = snapshot(remito)
                    antes['Estado_remito'] = remito.Estado_remito

                    # Revertir el ingreso: stock, lote y movimiento.
                    for lote_r in lotes_remito:
                        stock_r = stocks[lote_r.ID_Producto_id]
                        stock_r.Cantidad_stock -= lote_r.Cantidad_ingresada
                        stock_r.save(update_fields=['Cantidad_stock'])

                        MovimientosStock.objects.create(
                            ID_Usuario=usuario,
                            ID_Tipo_movimiento=tipo_anulacion,
                            ID_Lote=lote_r,
                            Cantidad_movimiento_stock=lote_r.Cantidad_ingresada,
                            Observaciones=(
                                f'Anulación del remito '
                                f'{remito.Numero_remito}: {motivo}'
                            )[:255]
                        )

                        lote_r.Cantidad_actual = 0
                        lote_r.save(update_fields=['Cantidad_actual'])

                    # El stock bajó: alerta si quedó en el mínimo o por debajo.
                    for stock_r in stocks.values():
                        revisar_stock(stock_r, usuario)

                    remito.Estado_remito = 'Anulado'
                    remito.Fecha_anulacion = timezone.now()
                    remito.Motivo_anulacion = motivo
                    remito.ID_Usuario_anulacion = usuario
                    remito.save(update_fields=[
                        'Estado_remito',
                        'Fecha_anulacion',
                        'Motivo_anulacion',
                        'ID_Usuario_anulacion',
                    ])

                    despues = snapshot(remito)
                    despues['Estado_remito'] = 'Anulado'
                    despues['Motivo_anulacion'] = motivo
                    despues['Lotes_revertidos'] = '; '.join(
                        f'{l.ID_Producto.Nombre_producto} lote {l.Numero_lote}: {l.Cantidad_ingresada} u.'
                        for l in lotes_remito
                    )

                    registrar_auditoria(
                        usuario,
                        'Remitos',
                        remito,
                        'ANULACION',
                        antes,
                        despues
                    )

                messages.success(
                    request,
                    f'El remito {remito.Numero_remito} fue anulado y se '
                    f'revirtió su ingreso de stock.'
                )

            except Remitos.DoesNotExist:
                messages.error(request, 'El remito seleccionado no existe.')

            except DatabaseError:
                messages.error(
                    request,
                    'Ocurrió un error en la base de datos. '
                    'No se guardaron los cambios.'
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
        .select_related('ID_Proveedor', 'ID_Usuario_anulacion')
        .prefetch_related('lotes__ID_Producto')
        .annotate(
            total_unidades=Coalesce(Sum('lotes__Cantidad_ingresada'), 0)
        )
        .order_by('-Fecha_remito', '-ID_Remito')
    )

    busqueda = request.GET.get('q', '').strip()
    proveedor_filtro = request.GET.get('proveedor', '').strip()
    estado_filtro = request.GET.get('estado', '').strip()

    if estado_filtro in ('Confirmado', 'Anulado'):
        remitos = remitos.filter(Estado_remito=estado_filtro)
    else:
        estado_filtro = ''

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
    ).prefetch_related(
        'proveedores'
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
            'estado_filtro': estado_filtro,
            'puede_anular': puede_accion(usuario, 'anular_remitos'),
            'puede_gestionar': puede(usuario, 'remitos', gestionar=True),
            'hoy': hoy,
        }
    )



@require_POST
def eliminar_usuario(request, pk):

    admin = usuario_con_acceso(request, 'usuarios', gestionar=True)

    if not admin:
        return redirect('panel_principal')

    usuario = get_object_or_404(Usuarios, ID_Usuario=pk)

    if usuario.ID_Usuario == admin.ID_Usuario:
        messages.error(request, 'No puede eliminarse a sí mismo.')
        return redirect('gestion_usuarios')

    nombre = usuario.Usuario

    try:
        with transaction.atomic():
            registrar_auditoria(admin, 'Usuarios', usuario, 'ELIMINACION', snapshot(usuario), {})
            usuario.delete()
    except ProtectedError:
        messages.error(
            request,
            f'No se puede eliminar al usuario "{nombre}": tiene '
            'registros de actividad asociados.'
        )
        return redirect('gestion_usuarios')

    messages.success(request, f'El usuario "{nombre}" fue eliminado.')

    return redirect('gestion_usuarios')


@require_POST
def eliminar_perfil(request, pk):

    usuario = usuario_con_acceso(request, 'perfiles', gestionar=True)

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
            registrar_auditoria(
                usuario, 'Perfiles', perfil, 'ELIMINACION',
                dict(snapshot(perfil), Permisos=', '.join(sorted(_permisos_de(perfil)))),
                {}
            )
            perfil.delete()    # sus permisos asignados se borran en cascada
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

    usuario = usuario_con_acceso(request, 'auditoria')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para consultar la auditoría.'
        )
        return redirect('panel_principal')

    entidad = request.GET.get('entidad', '').strip()
    accion = request.GET.get('accion', '').strip()
    usuario_id = request.GET.get('usuario', '').strip()
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()

    logs = LogAuditoria.objects.select_related(
        'ID_Usuario__ID_Perfil'
    ).order_by('-Fecha_hora')

    if entidad:
        logs = logs.filter(Seccion=entidad)

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
            'entidades': LogAuditoria.objects.order_by('Seccion').values_list(
                'Seccion', flat=True
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

# Campos que guardan el ID de otro registro: en pantalla se muestra su nombre.
_REFERENCIAS_AUDITORIA = {
    'ID_Tipo_producto': (TiposProductos, lambda o: o.Nombre_tipo_producto),
    'ID_Subtipo': (Subtipos, lambda o: o.Nombre_subtipo),
    'ID_Proveedor': (Proveedores, lambda o: o.nombre_proveedor),
    'ID_Producto': (Productos, lambda o: o.Nombre_producto),
    'ID_Remito': (Remitos, lambda o: o.Numero_remito),
    'ID_Perfil': (Perfiles, lambda o: o.Nombre_perfil),
    'ID_Usuario_anulacion': (
        Usuarios,
        lambda o: f'{o.Apellido_usuario}, {o.Nombre_usuario}'
    ),
    'ID_Usuario': (Usuarios, lambda o: f'{o.Apellido_usuario}, {o.Nombre_usuario}'),
    'ID_Stock': (Stock, lambda o: o.ID_Producto.Nombre_producto),
}


def _valor_visible_auditoria(campo, valor):
    """Reemplaza el ID de un registro relacionado por su nombre."""

    referencia = _REFERENCIAS_AUDITORIA.get(campo)

    if referencia is None or valor in (None, ''):
        return valor

    modelo, nombre = referencia
    objeto = modelo.objects.filter(pk=valor).first()

    return nombre(objeto) if objeto else 'Registro eliminado'


def detalle_auditoria(request, id_log):
    usuario = usuario_con_acceso(request, 'auditoria')

    if not usuario:
        return JsonResponse(
            {'error': 'No tenés permiso para consultar la auditoría.'},
            status=403
        )

    log = get_object_or_404(LogAuditoria, pk=id_log)

    # La fecha se guarda en UTC: se muestra en la hora local del sistema.
    fecha_local = timezone.localtime(log.Fecha_hora)

    anteriores = log.Valores_anteriores or {}
    actuales = log.Valores_actuales or {}

    # Qué se muestra en el detalle según la acción:
    #   datos   -> altas y eliminaciones: los datos del registro
    #   cambios -> modificaciones y anulaciones: valor anterior y nuevo
    #   ninguno -> inicio y cierre de sesión: nada más que los datos básicos
    ACCIONES_DATOS = (
        'CREACION', 'EGRESO_STOCK', 'INGRESO_LOTE', 'DESCARGA_PDF',
        'ENVIO_RECUPERACION',
    )

    if log.Accion in ACCIONES_DATOS:
        modo, origen = 'datos', actuales
    elif log.Accion == 'ELIMINACION':
        modo, origen = 'datos', anteriores
    elif log.Accion in ('INICIO_SESION', 'CIERRE_SESION'):
        modo, origen = 'ninguno', {}
    else:
        modo, origen = 'cambios', {}   # MODIFICACION, ANULACION, ASIGNACION_*

    return JsonResponse({
        'id': log.ID_Log,
        'fecha': fecha_local.strftime('%d/%m/%Y'),
        'hora': fecha_local.strftime('%H:%M'),
        'usuario': (
            f'{log.ID_Usuario.Apellido_usuario}, '
            f'{log.ID_Usuario.Nombre_usuario}'
            if log.ID_Usuario else 'Sistema'
        ),
        'perfil': (
            log.ID_Usuario.ID_Perfil.Nombre_perfil
            if log.ID_Usuario and log.ID_Usuario.ID_Perfil
            else 'Sin perfil'
        ),
        'entidad': log.Seccion,
        'registro': log.ID_Registro,
        'accion': log.Accion,
        'modo': modo,
        'datos': [
            {
                'campo': campo,
                'valor': _valor_visible_auditoria(campo, valor)
            }
            for campo, valor in sorted(origen.items())
        ],
        'anteriores': anteriores,
        'actuales': actuales,
        'cambios': [
            {
                'campo': campo,
                'antes': _valor_visible_auditoria(campo, antes),
                'despues': _valor_visible_auditoria(campo, despues)
            }
            for campo, antes, despues in log.cambios
        ] if modo == 'cambios' else []
    })

# ============================================================
# EGRESO DE STOCK
# ============================================================

TIPO_EGRESO = 'Egreso por venta'
TIPO_ANULACION_REMITO = 'Anulación de remito'
TIPO_ANULACION_EGRESO = 'Anulación de egreso'


def egreso_productos(request):
    """Compatibilidad: abre la vista de productos con el modal de egreso."""
    return redirect(f"{reverse('gestion_productos')}?egreso=1")


def _datos_egreso():
    """Productos activos con sus lotes vigentes (FEFO) para el modal."""

    hoy = timezone.localdate()

    productos = Productos.objects.filter(
        Estado_producto='Activo'
    ).select_related('stock').prefetch_related(
        Prefetch(
            'lotes',
            queryset=Lotes.objects.select_related(
                'ID_Remito',
                'ID_Remito__ID_Proveedor'
            ).filter(
                Cantidad_actual__gt=0,
                Fecha_vencimiento__gte=hoy
            ).order_by('Fecha_vencimiento', 'ID_Lote'),
            to_attr='lotes_disponibles'
        )
    ).order_by('Nombre_producto')

    datos = []

    for p in productos:
        if not p.lotes_disponibles:
            continue

        stock = getattr(p, 'stock', None)

        datos.append({
            'id': p.ID_Producto,
            'nombre': p.Nombre_producto,
            'stock': stock.Cantidad_stock if stock else 0,
            'stock_minimo': stock.Stock_minimo if stock else 0,
            'lotes': [
                {
                    'id': l.ID_Lote,
                    'numero': l.Numero_lote,
                    'remito': l.ID_Remito.Numero_remito,
                    'proveedor': l.ID_Remito.ID_Proveedor.nombre_proveedor,
                    'vence': l.Fecha_vencimiento.strftime('%d/%m/%Y'),
                    'cantidad': l.Cantidad_actual,
                }
                for l in p.lotes_disponibles
            ],
        })

    return datos


@require_POST
def registrar_egreso(request):
    """Registra un egreso por venta descontando de un lote específico."""

    usuario = usuario_con_acceso(request, 'egresos', gestionar=True)

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para registrar egresos de stock.'
        )
        return redirect('panel_principal')

    lote_id = request.POST.get('lote', '').strip()

    if not lote_id.isdigit():
        messages.error(request, 'Seleccioná un lote válido.')
        return redirect('gestion_productos')

    try:
        cantidad = int(request.POST.get('cantidad', '').strip())
    except (ValueError, TypeError):
        messages.error(request, 'La cantidad ingresada no es válida.')
        return redirect('gestion_productos')

    if cantidad <= 0:
        messages.error(request, 'La cantidad debe ser mayor a cero.')
        return redirect('gestion_productos')

    descripcion = request.POST.get('descripcion', '').strip()[:200]

    lote_base = Lotes.objects.filter(ID_Lote=lote_id).first()

    if not lote_base:
        messages.error(request, 'El lote seleccionado no existe.')
        return redirect('gestion_productos')

    tipo_egreso, _ = TiposMovimientos.objects.get_or_create(
        Nombre_tipo_movimiento=TIPO_EGRESO
    )

    hoy = timezone.localdate()
    stock_bajo = False

    try:
        with transaction.atomic():

            # Se bloquean stock y lote para evitar egresos simultáneos.
            stock = Stock.objects.select_for_update().filter(
                ID_Producto_id=lote_base.ID_Producto_id
            ).first()

            lote = Lotes.objects.select_for_update().get(
                ID_Lote=lote_id
            )

            producto = lote.ID_Producto

            if producto.Estado_producto != 'Activo':
                messages.error(request, 'El producto está inactivo.')
                return redirect('gestion_productos')

            if not stock:
                messages.error(
                    request,
                    'El producto no tiene stock registrado.'
                )
                return redirect('gestion_productos')

            if lote.Fecha_vencimiento < hoy:
                messages.error(
                    request,
                    'No se puede egresar de un lote vencido.'
                )
                return redirect('gestion_productos')

            if cantidad > lote.Cantidad_actual:
                messages.error(
                    request,
                    f'El lote {lote.Numero_lote} solo tiene '
                    f'{lote.Cantidad_actual} unidades disponibles.'
                )
                return redirect('gestion_productos')

            if cantidad > stock.Cantidad_stock:
                messages.error(
                    request,
                    'La cantidad supera el stock del producto.'
                )
                return redirect('gestion_productos')

            lote_antes = lote.Cantidad_actual
            stock_antes = stock.Cantidad_stock

            lote.Cantidad_actual -= cantidad
            lote.save(update_fields=['Cantidad_actual'])

            stock.Cantidad_stock -= cantidad
            stock.save(update_fields=['Cantidad_stock'])

            detalle = TIPO_EGRESO
            if descripcion:
                detalle = f'{TIPO_EGRESO}. {descripcion}'

            movimiento = MovimientosStock.objects.create(
                ID_Usuario=usuario,
                ID_Tipo_movimiento=tipo_egreso,
                ID_Lote=lote,
                Cantidad_movimiento_stock=cantidad,
                Observaciones=detalle[:255]
            )

            registrar_auditoria(
                usuario, 'Movimientos de Stock', movimiento, 'EGRESO_STOCK', {},
                {
                    'ID_Producto': producto.pk,
                    'Lote': lote.Numero_lote,
                    'Cantidad': cantidad,
                    'Lote_antes': lote_antes,
                    'Lote_despues': lote.Cantidad_actual,
                    'Stock_antes': stock_antes,
                    'Stock_despues': stock.Cantidad_stock,
                    'Observaciones': detalle[:255],
                }
            )

            stock_bajo = revisar_stock(stock, usuario)

    except DatabaseError:
        messages.error(
            request,
            'Ocurrió un error en la base de datos. '
            'No se registró el egreso.'
        )
        return redirect('gestion_productos')

    messages.success(
        request,
        f'Egreso registrado: {cantidad} unidad(es) de '
        f'"{producto.Nombre_producto}" (lote {lote.Numero_lote}). '
        f'Stock actual: {stock.Cantidad_stock}.'
    )

    if stock_bajo:
        messages.warning(
            request,
            f'Atención: "{producto.Nombre_producto}" está en o por '
            f'debajo del stock mínimo ({stock.Stock_minimo}).'
        )



    return redirect('gestion_productos')

@require_POST
def anular_egreso(request, id_movimiento):
    """Anula un egreso por venta hecho por error.

    No borra nada: marca el egreso como anulado, devuelve las unidades
    al lote y al stock del producto, genera un movimiento de
    "Anulación de egreso" y lo registra en la auditoría.
    """

    usuario = usuario_con_accion(request, 'anular_egresos')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para anular egresos de stock.'
        )
        return redirect('panel_principal')

    motivo = request.POST.get('Motivo_anulacion', '').strip()

    if len(motivo) < 10:
        messages.error(
            request,
            'Si anula este egreso debe justificarlo '
            '(mínimo 10 caracteres).'
        )
        return redirect('gestion_movimientos_stock')

    if len(motivo) > 200:
        messages.error(
            request,
            'La justificación no puede superar los 200 caracteres.'
        )
        return redirect('gestion_movimientos_stock')

    tipo_egreso = TiposMovimientos.objects.filter(
        Nombre_tipo_movimiento=TIPO_EGRESO
    ).first()

    hoy = timezone.localdate()

    try:
        with transaction.atomic():

            # 1) Se bloquea el egreso: dos usuarios no pueden anularlo a la vez.
            movimiento = MovimientosStock.objects.select_for_update().get(
                ID_Movimiento_stock=id_movimiento
            )

            if (
                not tipo_egreso
                or movimiento.ID_Tipo_movimiento_id != tipo_egreso.pk
                or not movimiento.ID_Lote_id
            ):
                messages.error(
                    request,
                    'Solo se pueden anular egresos por venta.'
                )
                return redirect('gestion_movimientos_stock')

            if movimiento.Anulado:
                messages.error(
                    request,
                    'Este egreso ya se encuentra anulado.'
                )
                return redirect('gestion_movimientos_stock')

            # 2) Se bloquean stock y lote (mismo orden que registrar_egreso).
            lote_base = Lotes.objects.get(ID_Lote=movimiento.ID_Lote_id)

            stock = Stock.objects.select_for_update().filter(
                ID_Producto_id=lote_base.ID_Producto_id
            ).first()

            lote = Lotes.objects.select_for_update().select_related(
                'ID_Producto', 'ID_Remito'
            ).get(ID_Lote=movimiento.ID_Lote_id)

            producto = lote.ID_Producto
            cantidad = movimiento.Cantidad_movimiento_stock

            if not stock:
                messages.error(
                    request,
                    'No se encontró el stock del producto.'
                )
                return redirect('gestion_movimientos_stock')

            if lote.ID_Remito.Estado_remito == 'Anulado':
                messages.error(
                    request,
                    'No se puede anular: el remito de este lote está anulado.'
                )
                return redirect('gestion_movimientos_stock')

            if lote.Fecha_vencimiento < hoy:
                messages.error(
                    request,
                    f'No se puede anular: el lote {lote.Numero_lote} ya '
                    'venció y las unidades devueltas no serían utilizables.'
                )
                return redirect('gestion_movimientos_stock')

            if lote.Cantidad_actual + cantidad > lote.Cantidad_ingresada:
                messages.error(
                    request,
                    'No se puede anular: la devolución dejaría al lote '
                    'con más unidades de las que ingresó.'
                )
                return redirect('gestion_movimientos_stock')

            lote_antes = lote.Cantidad_actual
            stock_antes = stock.Cantidad_stock

            # 3) Se devuelven las unidades al lote y al stock.
            lote.Cantidad_actual += cantidad
            lote.save(update_fields=['Cantidad_actual'])

            stock.Cantidad_stock += cantidad
            stock.save(update_fields=['Cantidad_stock'])

            # 4) Movimiento de anulación (suma) enlazado al egreso original.
            tipo_anulacion, _ = TiposMovimientos.objects.get_or_create(
                Nombre_tipo_movimiento=TIPO_ANULACION_EGRESO
            )

            contramovimiento = MovimientosStock.objects.create(
                ID_Usuario=usuario,
                ID_Tipo_movimiento=tipo_anulacion,
                ID_Lote=lote,
                Cantidad_movimiento_stock=cantidad,
                ID_Movimiento_origen=movimiento,
                Observaciones=(
                    f'Anulación del egreso N.º '
                    f'{movimiento.ID_Movimiento_stock}: {motivo}'
                )[:255]
            )

            # 5) El egreso original queda marcado, no se borra.
            movimiento.Anulado = True
            movimiento.Fecha_anulacion = timezone.now()
            movimiento.Motivo_anulacion = motivo
            movimiento.ID_Usuario_anulacion = usuario
            movimiento.save(update_fields=[
                'Anulado',
                'Fecha_anulacion',
                'Motivo_anulacion',
                'ID_Usuario_anulacion',
            ])

            # 6) Auditoría.
            registrar_auditoria(
                usuario,
                'Movimientos de Stock',
                movimiento,
                'ANULACION',
                {
                    'Estado': 'Vigente',
                    'Stock': stock_antes,
                    'Cantidad_lote': lote_antes,
                },
                {
                    'Estado': 'Anulado',
                    'Motivo_anulacion': motivo,
                    'ID_Producto': producto.pk,
                    'Lote': lote.Numero_lote,
                    'Cantidad_devuelta': cantidad,
                    'Stock': stock.Cantidad_stock,
                    'Cantidad_lote': lote.Cantidad_actual,
                    'Movimiento_de_anulacion': contramovimiento.pk,
                }
            )

    except MovimientosStock.DoesNotExist:
        messages.error(request, 'El movimiento seleccionado no existe.')
        return redirect('gestion_movimientos_stock')

    except IntegrityError:
        messages.error(
            request,
            'Este egreso ya fue anulado por otro usuario.'
        )
        return redirect('gestion_movimientos_stock')

    except DatabaseError:
        messages.error(
            request,
            'Ocurrió un error en la base de datos. '
            'No se anuló el egreso.'
        )
        return redirect('gestion_movimientos_stock')

    messages.success(
        request,
        f'Egreso anulado: se devolvieron {cantidad} unidad(es) de '
        f'"{producto.Nombre_producto}" (lote {lote.Numero_lote}). '
        f'Stock actual: {stock.Cantidad_stock}.'
    )

    return redirect('gestion_movimientos_stock')

# ============================================================
# REPORTES (solo Administrador)
# ============================================================

def gestion_reportes(request):

    usuario = usuario_con_acceso(request, 'reportes')

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para consultar los reportes.'
        )
        return redirect('panel_principal')

    return render(
        request,
        'inventario/reportes.html',
        {
            'usuario': usuario,
            'activo': 'reportes',
            'graficos': generar_reportes(TIPO_EGRESO),
        }
    )

def datos_evolucion(request):
    """Ventas e ingresos entre dos fechas (JSON, solo Administrador)."""

    if not usuario_con_acceso(request, 'reportes'):
        return JsonResponse(
            {'error': 'No tenés permiso para consultar los reportes.'},
            status=403
        )

    desde = _fecha_iso(request.GET.get('desde', ''))
    hasta = _fecha_iso(request.GET.get('hasta', ''))

    if not desde or not hasta:
        return JsonResponse(
            {'error': 'Las fechas ingresadas no son válidas.'},
            status=400
        )

    # No tiene sentido consultar fechas futuras.
    hasta = min(hasta, timezone.localdate())

    try:
        datos = datos_evolucion_rango(desde, hasta, TIPO_EGRESO)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse(datos)

# ============================================================
# BLOQUEO POR INACTIVIDAD
# ============================================================

def bloqueo_sesion(request):

    usuario = usuario_autenticado(request)

    if not usuario:
        return redirect('login')

    siguiente = (
        request.GET.get('next') or request.POST.get('next') or ''
    )

    if not siguiente or not url_has_allowed_host_and_scheme(
        siguiente, allowed_hosts={request.get_host()}
    ):
        siguiente = reverse('panel_principal')

    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    error = None

    if request.method == 'POST':

        usuario_ingresado = request.POST.get('usuario', '').strip()
        password = request.POST.get('password', '')

        if usuario_ingresado.lower() != usuario.Usuario.lower():
            error = 'Ingresá con el mismo usuario de la sesión bloqueada.'

        elif not check_password(password, usuario.Contrasena):
            error = 'Usuario o contraseña incorrectos.'

        else:
            request.session['bloqueada'] = False
            request.session['bloqueo_intentos'] = 0
            request.session['ultima_actividad'] = time_module.time()
            request.session.cycle_key()

            if es_ajax:
                return JsonResponse({'ok': True})

            return redirect(siguiente)

        intentos = request.session.get('bloqueo_intentos', 0) + 1
        request.session['bloqueo_intentos'] = intentos

        if intentos >= 5:
            request.session.flush()

            if es_ajax:
                return JsonResponse(
                    {'ok': False, 'cerrada': True,
                     'error': 'Demasiados intentos. Se cerró la sesión.'},
                    status=403
                )

            return redirect('login')

        if es_ajax:
            return JsonResponse({'ok': False, 'error': error}, status=400)

    return render(
        request,
        'inventario/bloqueo.html',
        {'usuario': usuario, 'error': error, 'siguiente': siguiente}
    )


def sesion_ping(request):
    """Mantiene viva la sesión mientras el usuario está activo en pantalla."""

    if not usuario_autenticado(request):
        return JsonResponse({'ok': False}, status=401)

    return JsonResponse({'ok': True})

# ============================================================
# RECUPERAR CONTRASEÑA (desde el login, sin sesión)
# ============================================================

def recuperar_contrasena(request):

    if request.method != 'POST':
        return render(request, 'inventario/recuperar_contrasena.html')

    email = request.POST.get('email', '').strip()
    contexto = {'email': email}

    if not email or '@' not in email:
        contexto['error'] = 'Ingresá un correo electrónico válido.'
        return render(request, 'inventario/recuperar_contrasena.html', contexto)

    if limite_superado(request, email):
        contexto['error'] = (
            'Hiciste demasiados pedidos. '
            'Esperá un rato antes de volver a intentarlo.'
        )
        return render(request, 'inventario/recuperar_contrasena.html', contexto)

    usuarios = list(
        Usuarios.objects.select_related('ID_Perfil').filter(
            Email_usuario__iexact=email
        )
    )

    habilitados = [u for u in usuarios if usuario_habilitado(u)]

    if habilitados:
        for u in habilitados:
            enviar_correo_recuperacion(u)
        contexto['enviado'] = True

    elif any(not u.Estado_usuario for u in usuarios):
        contexto['error'] = (
            'Tu usuario fue dado de baja. '
            'Comunicate con un administrador.'
        )

    elif usuarios:
        contexto['error'] = (
            'Tu usuario no está habilitado para ingresar. '
            'Comunicate con un administrador.'
        )

    else:
        # Correo inexistente: misma respuesta que si se hubiera enviado.
        contexto['enviado'] = True

    return render(request, 'inventario/recuperar_contrasena.html', contexto)


def recuperar_confirmar(request, uidb64, token):

    usuario = usuario_desde_uid(uidb64)

    if not usuario_habilitado(usuario) or not token_valido(usuario, token):
        return render(
            request,
            'inventario/recuperar_confirmar.html',
            {'invalido': True}
        )

    if request.method == 'POST':
        nueva = request.POST.get('nueva_contrasena', '')
        confirmar = request.POST.get('confirmar_contrasena', '')

        error = None

        if nueva != confirmar:
            error = 'Las contraseñas no coinciden.'
        else:
            error = validar_contrasena(nueva, usuario.Usuario)

        if error:
            return render(
                request,
                'inventario/recuperar_confirmar.html',
                {'error': error}
            )

        antes = snapshot(usuario)
        antes['Contrasena'] = 'anterior'

        usuario.Contrasena = make_password(nueva)
        usuario.Cambiar_contrasena = False
        usuario.save()

        despues = snapshot(usuario)
        despues['Contrasena'] = 'recuperada por correo'

        registrar_auditoria(
            usuario, 'Usuarios', usuario,
            'RECUPERA_CONTRASENA', antes, despues
        )

        messages.success(
            request,
            'Tu contraseña se cambió correctamente. Ya podés ingresar.'
        )

        return redirect('login')

    return render(request, 'inventario/recuperar_confirmar.html')
