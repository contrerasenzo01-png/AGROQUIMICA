import email
import hashlib
import re
import time as time_module
import unicodedata
from urllib import request
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.utils.http import url_has_allowed_host_and_scheme

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.http import JsonResponse
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.urls import reverse

from django.db.models import Count, F, Prefetch, ProtectedError, Q, RestrictedError, Sum
from django.db.models.functions import Coalesce

from PIL import Image, ImageOps, UnidentifiedImageError

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas
from .reportes import (
    generar_reportes, datos_evolucion_rango, datos_evolucion_12_meses,
)
from .pdf_remito import generar_pdf_remito
from .paginacion import paginar
from .alertas import (
    TIPO_STOCK, TIPOS_STOCK, TIPOS_VENTA,
    listar_notificaciones, mensaje_visible, revisar_stock,
    revisar_egreso_inusual,
    revisar_vencimientos as generar_alertas_vencimiento,
)
from .notificaciones import config
from .auditoria import (
    snapshot, registrar_auditoria, accion_por_estado,
    registrar_asignacion_perfil, registrar_asignacion_permisos,
    registrar_bloqueo_inactividad, nombre_registro,
)
from .forms import ProveedorForm
from .resumen import indicador
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

from .validaciones import (
    validar_nombre, validar_persona, validar_texto, validar_codigo,
    validar_entero, validar_decimal, validar_dni, validar_email,
    validar_fecha, validar_usuario_login, validar_contrasena_login,
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
    """Inicio de sesión.

    Primero valida el formato de cada campo por separado (los errores
    se muestran en rojo debajo del campo). Recién si los dos están bien
    busca el usuario. Si la contraseña no coincide, el mensaje es
    siempre el mismo para no revelar qué usuarios existen.
    """

    error_message = None
    errores = {}
    usuario_ingresado = ''

    if request.method == 'POST':

        usuario_input, error_usuario = validar_usuario_login(
            request.POST.get('usuario', '')
        )
        password_input, error_password = validar_contrasena_login(
            request.POST.get('password', '')
        )

        # Se devuelve al formulario lo que escribió (nunca la contraseña).
        usuario_ingresado = usuario_input

        if error_usuario:
            errores['usuario'] = error_usuario

        if error_password:
            errores['password'] = error_password

        if not errores:

            usuario = Usuarios.objects.select_related(
                'ID_Perfil'
            ).filter(
                Usuario=usuario_input
            ).first()

            # La contraseña se verifica ANTES que el estado: así,
            # quien no la conoce no puede averiguar si un usuario
            # existe o está inactivo.
            if not usuario or not check_password(
                password_input,
                usuario.Contrasena
            ):
                error_message = 'Usuario o contraseña incorrectos.'

            elif not usuario.Estado_usuario:
                error_message = (
                    'Su usuario se encuentra inactivo. '
                    'Comuníquese con el administrador.'
                )

            elif not usuario.ID_Perfil or not usuario.ID_Perfil.Estado_perfil:
                error_message = (
                    'Su perfil no está habilitado. '
                    'Comuníquese con el administrador.'
                )

            else:
                # Nueva sesión: evita reutilizar un id de sesión anterior.
                request.session.cycle_key()

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

    return render(
        request,
        'inventario/login.html',
        {
            'error': error_message,
            'errores': errores,
            'usuario_ingresado': usuario_ingresado,
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


def movimientos_visibles(queryset, usuario):
    """El administrador ve todos los movimientos de stock;
    el resto de los usuarios solo los que registraron ellos mismos."""
    if usuario.ID_Perfil.Nombre_perfil in PERFILES_ADMIN:
        return queryset
    return queryset.filter(ID_Usuario=usuario)

def alertas_visibles(usuario):
    """El administrador ve todo el historial de alertas; el resto de los
    usuarios ve las pendientes (cualquiera puede atenderlas) y las que
    atendió él mismo."""
    alertas = Alertas.objects.select_related(
        'ID_Stock',
        'ID_Stock__ID_Producto',
        'ID_Usuario'
    )

    if usuario.ID_Perfil.Nombre_perfil in PERFILES_ADMIN:
        return alertas

    return alertas.filter(Q(Atendida=False) | Q(ID_Usuario=usuario))


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
    grafico = {'mas': [], 'menos': [], 'sin_ventas': 0}
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

        # Unidades vendidas por producto activo (todo el historial).
        # Venta = egreso por venta no anulado, igual que en los
        # reportes consolidados.
        vendidos = (
            MovimientosStock.objects.filter(
                Anulado=False,
                ID_Tipo_movimiento__Nombre_tipo_movimiento__in=TIPOS_VENTA,
                ID_Lote__isnull=False,
                ID_Lote__ID_Producto__Estado_producto='Activo',
            )
            .values('ID_Lote__ID_Producto', 'ID_Lote__ID_Producto__Nombre_producto')
            .annotate(cantidad=Sum('Cantidad_movimiento_stock'))
        )

        ventas = [
            {
                'nombre': v['ID_Lote__ID_Producto__Nombre_producto'],
                'cantidad': v['cantidad'],
            }
            for v in vendidos
            if v['cantidad'] and v['cantidad'] > 0
        ]

        productos_activos = Productos.objects.filter(Estado_producto='Activo').count()

        grafico = {
            'mas': sorted(ventas, key=lambda d: (-d['cantidad'], d['nombre']))[:5],
            'menos': sorted(ventas, key=lambda d: (d['cantidad'], d['nombre']))[:5],
            'sin_ventas': max(productos_activos - len(ventas), 0),
        }

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
        ultimos = movimientos_visibles(
            MovimientosStock.objects.select_related(
                'ID_Tipo_movimiento',
                'ID_Lote',
                'ID_Lote__ID_Producto',
                'ID_Usuario',
            ),
            usuario
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


def _render_proveedores(
    request,
    usuario,
    form_crear=None,
    form_editar=None,
    proveedor_editar=None,
    modal_abierto=None
):
    """
    Prepara los datos y muestra la pantalla de proveedores.
    Se utiliza desde las funciones de consulta, creación y edición.
    """

    # --------------------------------------------------------
    # BÚSQUEDA
    # --------------------------------------------------------

    busqueda = request.GET.get('q', '').strip()

    proveedores = Proveedores.objects.all()

    if busqueda:
        proveedores = proveedores.filter(
            Q(nombre_proveedor__icontains=busqueda) |
            Q(email_proveedor__icontains=busqueda) |
            Q(direccion_proveedor__icontains=busqueda) |
            Q(telefono_proveedor__icontains=busqueda)
        )

    # --------------------------------------------------------
    # VERIFICAR SI LOS PROVEEDORES SE PUEDEN ELIMINAR
    # --------------------------------------------------------

    # Proveedores que tienen remitos registrados.
    con_remitos = set(
        Remitos.objects.values_list(
            'ID_Proveedor', flat=True
        )
    )

    # Proveedores asociados a productos.
    con_productos = set(
        Productos.objects.filter(
            proveedores__isnull=False
        ).values_list('proveedores', flat=True)
    )

    proveedores = list(proveedores)

    # Un proveedor solo puede eliminarse si nunca se utilizó.
    for proveedor in proveedores:
        vinculos = []
        if proveedor.pk in con_remitos:
            vinculos.append('remitos registrados')
        if proveedor.pk in con_productos:
            vinculos.append('productos asociados')

        proveedor.eliminable = not vinculos
        proveedor.motivo_no_eliminable = (
            'No se puede eliminar: tiene ' + ' y '.join(vinculos)
            if vinculos else ''
        )

    # --------------------------------------------------------
    # FORMULARIOS
    # --------------------------------------------------------

    if form_crear is None:
        form_crear = ProveedorForm()

    if form_editar is None:
        form_editar = ProveedorForm(
            instance=proveedor_editar
        )

    # --------------------------------------------------------
    # MOSTRAR PANTALLA
    # --------------------------------------------------------

    return render(
        request,
        'inventario/proveedores.html',
        {
            'usuario': usuario,
            'proveedores': proveedores,

            'total_proveedores': Proveedores.objects.count(),

            'resumen': [
                indicador(Proveedores.objects.count(), 'Proveedores registrados', 'verde', 'camion'),
                indicador(Proveedores.objects.filter(estado_proveedor=True).count(), 'Activos', 'azul', 'check'),
                indicador(Proveedores.objects.filter(estado_proveedor=False).count(), 'Inactivos', 'rojo', 'pausa'),
                indicador(len(con_remitos), 'Con remitos registrados', 'ambar', 'documento'),
            ],

            'proveedores_activos': Proveedores.objects.filter(
                estado_proveedor=True
            ).count(),

            # Formularios separados para crear y editar.
            'form_crear': form_crear,
            'form_editar': form_editar,

            # Compatibilidad con la variable anterior.
            'form': form_crear,

            # Datos necesarios para abrir el modal de edición.
            'proveedor_editar': proveedor_editar,
            'modal_abierto': modal_abierto,

            'busqueda': busqueda,
        }
    )


# ============================================================
# CONSULTAR PROVEEDORES
# ============================================================

def gestion_proveedores(request):
    """Muestra la pantalla principal de proveedores."""

    usuario = usuario_con_acceso(
        request,
        'proveedores'
    )

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para consultar proveedores.'
        )
        return redirect('panel_principal')

    return _render_proveedores(
        request,
        usuario
    )


# ============================================================
# CREAR PROVEEDOR
# ============================================================

def crear_proveedor(request):

    usuario = usuario_con_acceso(
        request,
        'proveedores',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para crear proveedores.'
        )
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_proveedores')

    # Recibir los datos del formulario.
    form = ProveedorForm(request.POST)

    # Si existen errores, mostrar nuevamente la pantalla
    # conservando los datos y los mensajes debajo de los campos.
    if not form.is_valid():

        return _render_proveedores(
            request,
            usuario,
            form_crear=form,
            modal_abierto='crear'
        )

    try:
        with transaction.atomic():

            proveedor = form.save()

            # Registrar la creación en la auditoría.
            registrar_auditoria(
                usuario,
                'Proveedores',
                proveedor,
                'CREACION',
                {},
                snapshot(proveedor)
            )

    except IntegrityError:

        form.add_error(
            None,
            'No se pudo registrar el proveedor. '
            'Verifique que el nombre no esté registrado.'
        )

        return _render_proveedores(
            request,
            usuario,
            form_crear=form,
            modal_abierto='crear'
        )

    messages.success(
        request,
        'Proveedor registrado correctamente.'
    )

    return redirect('gestion_proveedores')


# ============================================================
# EDITAR PROVEEDOR
# ============================================================

def editar_proveedor(request, pk):

    usuario = usuario_con_acceso(
        request,
        'proveedores',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para editar proveedores.'
        )
        return redirect('panel_principal')

    proveedor = get_object_or_404(
        Proveedores,
        ID_Proveedor=pk
    )

    if request.method != 'POST':
        return redirect('gestion_proveedores')

    # Guardar los datos anteriores para la auditoría.
    antes = snapshot(proveedor)

    estado_original = proveedor.estado_proveedor

    # Vincular el formulario con el proveedor seleccionado.
    form = ProveedorForm(
        request.POST,
        instance=proveedor
    )

    # Si hay errores, conservar los datos ingresados
    # y volver a abrir el modal de edición.
    if not form.is_valid():

        return _render_proveedores(
            request,
            usuario,
            form_editar=form,
            proveedor_editar=proveedor,
            modal_abierto='editar'
        )

    proveedor_actualizado = form.save(commit=False)

    # El estado se modifica únicamente desde
    # cambiar_estado_proveedor.
    proveedor_actualizado.estado_proveedor = estado_original

    despues = snapshot(proveedor_actualizado)

    # Verificar si realmente hubo modificaciones.
    if antes == despues:

        messages.info(
            request,
            'No se realizaron cambios en los datos del proveedor.'
        )

        return redirect('gestion_proveedores')

    try:
        with transaction.atomic():

            proveedor_actualizado.save()

            # Registrar la modificación en la auditoría.
            registrar_auditoria(
                usuario,
                'Proveedores',
                proveedor_actualizado,
                'MODIFICACION',
                antes,
                snapshot(proveedor_actualizado)
            )

    except IntegrityError:

        form.add_error(
            None,
            'No se pudo actualizar el proveedor. '
            'Verifique que el nombre no esté registrado.'
        )

        return _render_proveedores(
            request,
            usuario,
            form_editar=form,
            proveedor_editar=proveedor,
            modal_abierto='editar'
        )

    messages.success(
        request,
        'Proveedor actualizado correctamente.'
    )

    return redirect('gestion_proveedores')


# ============================================================
# ELIMINAR PROVEEDOR
# ============================================================

@require_POST
def eliminar_proveedor(request, pk):
    """Elimina un proveedor únicamente si nunca se utilizó."""

    usuario = usuario_con_acceso(
        request,
        'proveedores',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para eliminar proveedores.'
        )
        return redirect('panel_principal')

    proveedor = get_object_or_404(
        Proveedores,
        ID_Proveedor=pk
    )

    nombre = proveedor.nombre_proveedor

    # Verificar si tiene remitos asociados.
    if Remitos.objects.filter(
        ID_Proveedor=proveedor
    ).exists():

        messages.error(
            request,
            f'No se puede eliminar el proveedor "{nombre}" '
            'porque tiene remitos registrados. Puede darlo de baja.'
        )

        return redirect('gestion_proveedores')

    # Verificar si tiene productos asociados.
    if Productos.objects.filter(
        proveedores=proveedor
    ).exists():

        messages.error(
            request,
            f'No se puede eliminar el proveedor "{nombre}" '
            'porque tiene productos asociados. Puede darlo de baja.'
        )

        return redirect('gestion_proveedores')

    try:
        with transaction.atomic():

            # Registrar la eliminación en la auditoría.
            registrar_auditoria(
                usuario,
                'Proveedores',
                proveedor,
                'ELIMINACION',
                snapshot(proveedor),
                {}
            )

            proveedor.delete()

    except (
        ProtectedError,
        RestrictedError,
        IntegrityError
    ):

        messages.error(
            request,
            f'No se puede eliminar el proveedor "{nombre}" '
            'porque tiene registros asociados. Puede darlo de baja.'
        )

        return redirect('gestion_proveedores')

    messages.success(
        request,
        f'El proveedor "{nombre}" fue eliminado.'
    )

    return redirect('gestion_proveedores')



# ============================================================
# CAMBIAR ESTADO DEL PROVEEDOR
# ============================================================

def _resumen_proveedores():
    """Totales que se actualizan en las tarjetas al dar de baja o activar."""

    total = Proveedores.objects.count()
    activos = Proveedores.objects.filter(estado_proveedor=True).count()

    return {
        'total': total,
        'activos': activos,
        'inactivos': total - activos,
    }


@require_POST
def cambiar_estado_proveedor(request, pk):
    """Permite activar o dar de baja un proveedor."""

    es_ajax = (
        request.headers.get('X-Requested-With')
        == 'XMLHttpRequest'
    )

    # --------------------------------------------------------
    # RESPUESTA ANTE ERRORES
    # --------------------------------------------------------

    def responder_error(texto, status):

        if es_ajax:
            return JsonResponse(
                {
                    'ok': False,
                    'error': texto
                },
                status=status
            )

        messages.error(request, texto)

        return redirect('gestion_proveedores')

    # --------------------------------------------------------
    # VERIFICAR PERMISOS
    # --------------------------------------------------------

    usuario = usuario_con_acceso(
        request,
        'proveedores',
        gestionar=True
    )

    if not usuario:

        if es_ajax:
            return JsonResponse(
                {
                    'ok': False,
                    'error': (
                        'No tiene permiso para cambiar '
                        'el estado de proveedores.'
                    )
                },
                status=403
            )

        messages.error(
            request,
            'No tiene permiso para cambiar el estado de proveedores.'
        )

        return redirect('panel_principal')

    # --------------------------------------------------------
    # BUSCAR PROVEEDOR
    # --------------------------------------------------------

    proveedor = Proveedores.objects.filter(
        ID_Proveedor=pk
    ).first()

    if not proveedor:
        return responder_error(
            'El proveedor seleccionado no existe.',
            404
        )

    # --------------------------------------------------------
    # VALIDAR ESTADO SOLICITADO
    # --------------------------------------------------------

    estado_solicitado = request.POST.get(
        'estado',
        ''
    ).strip().lower()

    if estado_solicitado not in ('activo', 'inactivo'):

        return responder_error(
            'El estado solicitado no es válido.',
            400
        )

    nuevo_estado = estado_solicitado == 'activo'

    # --------------------------------------------------------
    # VERIFICAR SI EL ESTADO YA ES EL MISMO
    # --------------------------------------------------------

    if proveedor.estado_proveedor == nuevo_estado:

        mensaje = (
            'El proveedor ya se encuentra activo.'
            if nuevo_estado
            else 'El proveedor ya se encuentra inactivo.'
        )

        if es_ajax:
            return JsonResponse({
                'ok': True,
                'mensaje': mensaje,
                'activo': proveedor.estado_proveedor,
                'resumen': _resumen_proveedores(),
            })

        messages.info(request, mensaje)

        return redirect('gestion_proveedores')

    # --------------------------------------------------------
    # ACTUALIZAR ESTADO
    # --------------------------------------------------------

    antes = snapshot(proveedor)

    proveedor.estado_proveedor = nuevo_estado

    mensaje = (
        f'El proveedor "{proveedor.nombre_proveedor}" '
        'fue activado correctamente.'
        if nuevo_estado
        else
        f'El proveedor "{proveedor.nombre_proveedor}" '
        'fue dado de baja correctamente.'
    )

    try:
        with transaction.atomic():

            proveedor.save(
                update_fields=['estado_proveedor']
            )

            # Registrar el cambio en la auditoría.
            registrar_auditoria(
                usuario,
                'Proveedores',
                proveedor,
                'ACTIVACION' if nuevo_estado else 'BAJA',
                antes,
                snapshot(proveedor)
            )

    except IntegrityError:

        return responder_error(
            'No se pudo actualizar el estado del proveedor.',
            400
        )

    # --------------------------------------------------------
    # RESPUESTA
    # --------------------------------------------------------

    if es_ajax:
        return JsonResponse({
            'ok': True,
            'mensaje': mensaje,
            'activo': proveedor.estado_proveedor,
            'resumen': _resumen_proveedores(),
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
            'No tiene permiso para consultar tipos de productos.'
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
            'resumen': [
                indicador(TiposProductos.objects.count(), 'Tipos de producto', 'verde', 'etiqueta'),
                indicador(TiposProductos.objects.filter(Estado_tipo_producto=True).count(), 'Activos', 'azul', 'check'),
                indicador(TiposProductos.objects.filter(Estado_tipo_producto=False).count(), 'Inactivos', 'rojo', 'pausa'),
                indicador(Subtipos.objects.count(), 'Subtipos', 'ambar', 'capas'),
            ],
        }
    )

# ============================================================
# CREAR TIPO DE PRODUCTO
# ============================================================

def crear_tipo_producto(request):

    usuario = usuario_con_acceso(request, 'tipos', gestionar=True)

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para gestionar tipos de productos.'
        )
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_tipos_productos')

    nombre, error = validar_nombre(
        request.POST.get('Nombre_tipo_producto', ''),
        'Nombre del tipo de producto', 2, 50
    )

    if error:
        messages.error(request, error)
        return redirect('gestion_tipos_productos')

    if TiposProductos.objects.filter(
        Nombre_tipo_producto__iexact=nombre
    ).exists():
        messages.error(
            request,
            'Ya existe un tipo de producto con ese nombre.'
        )
        return redirect('gestion_tipos_productos')

    tipo = TiposProductos.objects.create(
        Nombre_tipo_producto=nombre,
        Estado_tipo_producto=True
    )

    registrar_auditoria(
        usuario, 'Tipos de productos', tipo, 'CREACION', {}, snapshot(tipo)
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

    usuario = usuario_con_acceso(request, 'tipos', gestionar=True)

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para gestionar tipos de productos.'
        )
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_tipos_productos')

    tipo = get_object_or_404(TiposProductos, ID_Tipo_producto=pk)

    antes = snapshot(tipo)

    nombre, error = validar_nombre(
        request.POST.get('Nombre_tipo_producto', ''),
        'Nombre del tipo de producto', 2, 50
    )

    if error:
        messages.error(request, error)
        return redirect('gestion_tipos_productos')

    estado_recibido = request.POST.get('Estado_tipo_producto', '')

    if estado_recibido not in ('True', 'False'):
        messages.error(request, 'El estado seleccionado no es válido.')
        return redirect('gestion_tipos_productos')

    if TiposProductos.objects.filter(
        Nombre_tipo_producto__iexact=nombre
    ).exclude(ID_Tipo_producto=pk).exists():
        messages.error(
            request,
            'Ya existe otro tipo de producto con ese nombre.'
        )
        return redirect('gestion_tipos_productos')

    tipo.Nombre_tipo_producto = nombre
    tipo.Estado_tipo_producto = (estado_recibido == 'True')
    tipo.save(
        update_fields=['Nombre_tipo_producto', 'Estado_tipo_producto']
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
            'No tiene permiso para gestionar tipos de productos.'
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
            'No tiene permiso para consultar subtipos.'
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

    # Todos los tipos: al registrar solo se ofrecen los activos y al
    # editar se conserva el tipo inactivo que el subtipo ya tenía.
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
            'total_subtipos': Subtipos.objects.count(),
            'resumen': [
                indicador(Subtipos.objects.count(), 'Subtipos', 'verde', 'capas'),
                indicador(TiposProductos.objects.count(), 'Tipos de producto', 'azul', 'etiqueta'),
                indicador(len(productos_por_subtipo), 'Con productos', 'ambar', 'caja'),
                indicador(
                    Subtipos.objects.exclude(pk__in=list(productos_por_subtipo)).count(),
                    'Sin productos', 'rojo', 'pausa'
                ),
            ],
        }
    )


def crear_subtipo(request):

    usuario = usuario_con_acceso(request, 'subtipos', gestionar=True)

    if not usuario:
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_subtipos')

    nombre, error = validar_nombre(
        request.POST.get('Nombre_subtipo', ''),
        'Nombre del subtipo', 2, 50
    )

    if error:
        messages.error(request, error)
        return redirect('gestion_subtipos')

    descripcion, error = validar_texto(
        request.POST.get('Descripcion_subtipo', ''),
        'Descripción', maximo=200, obligatorio=False
    )

    if error:
        messages.error(request, error)
        return redirect('gestion_subtipos')

    tipo_id = request.POST.get('ID_Tipo_producto', '').strip()

    if not tipo_id.isdigit():
        messages.error(request, 'Debe seleccionar un tipo de producto.')
        return redirect('gestion_subtipos')

    tipo = get_object_or_404(TiposProductos, ID_Tipo_producto=tipo_id)

    # No permitir asociar subtipos a tipos inactivos
    if not tipo.Estado_tipo_producto:
        messages.error(
            request,
            'No se pueden asociar subtipos a un tipo de producto inactivo.'
        )
        return redirect('gestion_subtipos')

    if Subtipos.objects.filter(
        ID_Tipo_producto=tipo,
        Nombre_subtipo__iexact=nombre
    ).exists():
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
        datos_subtipo['Descripcion_subtipo'] = descripcion or None

    subtipo = Subtipos.objects.create(**datos_subtipo)

    registrar_auditoria(
        usuario, 'Subtipos', subtipo, 'CREACION', {}, snapshot(subtipo)
    )

    messages.success(request, 'Subtipo creado correctamente.')

    return redirect('gestion_subtipos')


def editar_subtipo(request, pk):

    usuario = usuario_con_acceso(request, 'subtipos', gestionar=True)

    if not usuario:
        return redirect('panel_principal')

    subtipo = get_object_or_404(Subtipos, ID_Subtipo=pk)

    if request.method != 'POST':
        return redirect('gestion_subtipos')

    antes = snapshot(subtipo)

    nombre, error = validar_nombre(
        request.POST.get('Nombre_subtipo', ''),
        'Nombre del subtipo', 2, 50
    )

    if error:
        messages.error(request, error)
        return redirect('gestion_subtipos')

    descripcion, error = validar_texto(
        request.POST.get('Descripcion_subtipo', ''),
        'Descripción', maximo=200, obligatorio=False
    )

    if error:
        messages.error(request, error)
        return redirect('gestion_subtipos')

    tipo_id = request.POST.get('ID_Tipo_producto', '').strip()

    if not tipo_id.isdigit():
        messages.error(request, 'Debe seleccionar un tipo de producto.')
        return redirect('gestion_subtipos')

    tipo = get_object_or_404(TiposProductos, ID_Tipo_producto=tipo_id)

    # Se permite conservar el tipo inactivo que el subtipo ya tenía.
    if (
        not tipo.Estado_tipo_producto
        and tipo.pk != subtipo.ID_Tipo_producto_id
    ):
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

    if Subtipos.objects.filter(
        ID_Tipo_producto=tipo,
        Nombre_subtipo__iexact=nombre
    ).exclude(ID_Subtipo=pk).exists():
        messages.error(
            request,
            'Ya existe un subtipo con ese nombre '
            'para el tipo seleccionado.'
        )
        return redirect('gestion_subtipos')

    subtipo.ID_Tipo_producto = tipo
    subtipo.Nombre_subtipo = nombre

    if _subtipo_tiene_descripcion():
        subtipo.Descripcion_subtipo = descripcion or None

    subtipo.save()

    registrar_auditoria(
        usuario, 'Subtipos', subtipo, 'MODIFICACION', antes, snapshot(subtipo)
    )

    messages.success(request, 'Subtipo modificado correctamente.')

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
            'usuario': usuario,
            # Solo el administrador ve las fotos de los demás usuarios.
            'ver_fotos': usuario.ID_Perfil.Nombre_perfil in PERFILES_ADMIN,
            'resumen': [
                indicador(Usuarios.objects.count(), 'Usuarios registrados', 'verde', 'usuarios'),
                indicador(Usuarios.objects.filter(Estado_usuario=True).count(), 'Activos', 'azul', 'check'),
                indicador(Usuarios.objects.filter(Estado_usuario=False).count(), 'Inactivos', 'rojo', 'pausa'),
                indicador(
                    Usuarios.objects.filter(Estado_usuario=True, Cambiar_contrasena=True).count(),
                    'Deben cambiar la contraseña', 'ambar', 'llave'
                ),
            ],
        }
    )


# ============================================================
# REGLAS DE LA CONTRASEÑA
# Se usan al crear un usuario, al restablecer, al cambiar
# y al recuperar la contraseña por correo.
# ============================================================

def validar_contrasena(contrasena, usuario=''):
    """Devuelve un mensaje de error, o None si la contraseña es válida.

    Primero se avisa de los dos casos puntuales (espacios y nombre de
    usuario); cualquier otro requisito incumplido (largo, mayúscula,
    minúscula o número) devuelve un mensaje general.
    """

    if re.search(r'\s', contrasena):
        return 'No se pueden usar espacios.'
    if usuario and usuario.lower() in contrasena.lower():
        return 'No se puede usar el nombre de usuario.'
    if (
        len(contrasena) < 8
        or len(contrasena) > 64
        or not re.search(r'[A-Z]', contrasena)
        or not re.search(r'[a-z]', contrasena)
        or not re.search(r'\d', contrasena)
    ):
        return 'La contraseña no cumplió con los requerimientos solicitados.'
    return None


def _errores_nueva_contrasena(nueva, confirmar, usuario):
    """Errores por campo al elegir una contraseña nueva.

    Devuelve {'nueva_contrasena': ..., 'confirmar_contrasena': ...}
    solo con los campos que tienen error (vacío si está todo bien).
    """

    errores = {}

    if not nueva:
        errores['nueva_contrasena'] = 'Ingrese la nueva contraseña.'
    else:
        error = validar_contrasena(nueva, usuario.Usuario)

        if error:
            errores['nueva_contrasena'] = error
        elif check_password(nueva, usuario.Contrasena):
            errores['nueva_contrasena'] = (
                'La contraseña no puede ser igual a la anterior.'
            )

    if not confirmar:
        errores['confirmar_contrasena'] = 'Repita la nueva contraseña.'
    elif confirmar != nueva:
        errores['confirmar_contrasena'] = 'Las contraseñas no coinciden.'

    return errores


def crear_usuario(request):

    usuario_admin = usuario_con_acceso(request, 'usuarios', gestionar=True)

    if not usuario_admin:
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_usuarios')

    # --------------------------------------------------------
    # PERFIL
    # --------------------------------------------------------

    perfil_id = request.POST.get('ID_Perfil', '').strip()

    if not perfil_id.isdigit():
        messages.error(request, 'Debe seleccionar un perfil.')
        return redirect('gestion_usuarios')

    perfil = get_object_or_404(Perfiles, ID_Perfil=perfil_id)

    if not perfil.Estado_perfil:
        messages.error(
            request,
            'No se pueden registrar usuarios con un perfil inactivo.'
        )
        return redirect('gestion_usuarios')

    # --------------------------------------------------------
    # DATOS PERSONALES
    # --------------------------------------------------------

    nombre, error = validar_persona(
        request.POST.get('Nombre_usuario', ''), 'Nombre'
    )
    if error:
        messages.error(request, error)
        return redirect('gestion_usuarios')

    apellido, error = validar_persona(
        request.POST.get('Apellido_usuario', ''), 'Apellido'
    )
    if error:
        messages.error(request, error)
        return redirect('gestion_usuarios')

    dni, error = validar_dni(request.POST.get('DNI', ''))
    if error:
        messages.error(request, error)
        return redirect('gestion_usuarios')

    email, error = validar_email(request.POST.get('Email_usuario', ''))
    if error:
        messages.error(request, error)
        return redirect('gestion_usuarios')

    if Usuarios.objects.filter(DNI=dni).exists():
        messages.error(request, 'Ya existe un usuario con ese DNI.')
        return redirect('gestion_usuarios')

    if Usuarios.objects.filter(Email_usuario__iexact=email).exists():
        messages.error(
            request,
            'Ya existe un usuario con ese correo electrónico.'
        )
        return redirect('gestion_usuarios')

    # --------------------------------------------------------
    # NOMBRE DE USUARIO: apellido + primera letra del nombre,
    # sin tildes, sin espacios ni símbolos.
    # --------------------------------------------------------

    def sin_tildes(texto):
        return ''.join(
            c for c in unicodedata.normalize('NFD', texto)
            if unicodedata.category(c) != 'Mn'
        )

    usuario_generado = re.sub(
        r'[^a-z0-9]', '',
        (sin_tildes(apellido) + sin_tildes(nombre)[0]).lower()
    )[:50]

    if not usuario_generado:
        messages.error(
            request,
            'No se pudo generar el nombre de usuario con esos datos.'
        )
        return redirect('gestion_usuarios')

    if Usuarios.objects.filter(Usuario=usuario_generado).exists():
        messages.error(
            request,
            f'El usuario {usuario_generado} ya existe.'
        )
        return redirect('gestion_usuarios')

    # --------------------------------------------------------
    # CONTRASEÑA (sin .strip(): si tiene espacios, se rechaza)
    # --------------------------------------------------------

    contrasena = request.POST.get('Contrasena', '')

    error = validar_contrasena(contrasena, usuario_generado)

    if error:
        messages.error(request, error)
        return redirect('gestion_usuarios')

    nuevo = Usuarios.objects.create(
        ID_Perfil=perfil,
        DNI=dni,
        Apellido_usuario=apellido,
        Nombre_usuario=nombre,
        Usuario=usuario_generado,
        Contrasena=make_password(contrasena),
        Email_usuario=email,
        Estado_usuario=True,
        Cambiar_contrasena=True
    )

    registrar_auditoria(
        usuario_admin, 'Usuarios', nuevo, 'CREACION', {}, snapshot(nuevo)
    )
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

    if request.method != 'POST':
        return redirect('gestion_usuarios')

    usuario_editado = get_object_or_404(Usuarios, ID_Usuario=pk)

    antes = snapshot(usuario_editado)

    nuevo_email, error = validar_email(request.POST.get('Email_usuario', ''))

    if error:
        messages.error(request, error)
        return redirect('gestion_usuarios')

    if Usuarios.objects.filter(
        Email_usuario__iexact=nuevo_email
    ).exclude(ID_Usuario=pk).exists():
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
    """Pantalla "Debe cambiar su contraseña" (después de una temporal).

    Los errores se devuelven por campo para mostrarlos en rojo
    debajo de cada uno (errores.nueva_contrasena / confirmar_contrasena).
    """

    usuario = usuario_autenticado(request)

    if not usuario:
        request.session.flush()
        return redirect('login')

    if request.method == 'POST':
        nueva_contrasena = request.POST.get('nueva_contrasena', '')
        confirmar_contrasena = request.POST.get('confirmar_contrasena', '')

        errores = _errores_nueva_contrasena(
            nueva_contrasena, confirmar_contrasena, usuario
        )

        if errores:
            return render(
                request,
                'inventario/cambiar_contrasena.html',
                {'usuario': usuario, 'errores': errores}
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
            'resumen': [
                indicador(Perfiles.objects.count(), 'Perfiles de acceso', 'verde', 'escudo'),
                indicador(Perfiles.objects.filter(Estado_perfil=True).count(), 'Activos', 'azul', 'check'),
                indicador(Perfiles.objects.filter(Estado_perfil=False).count(), 'Inactivos', 'rojo', 'pausa'),
                indicador(
                    Usuarios.objects.filter(Estado_usuario=True, ID_Perfil__isnull=False).count(),
                    'Usuarios activos asignados', 'ambar', 'usuarios'
                ),
            ],
        }
    )


def crear_perfil(request):

    usuario = usuario_con_acceso(request, 'perfiles', gestionar=True)

    if not usuario:
        return redirect('panel_principal')

    if request.method == 'POST':

        nombre_perfil, error = validar_nombre(
            request.POST.get('Nombre_perfil', ''),
            'Nombre del perfil', 3, 50
        )

        if error:
            messages.error(request, error)
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
            'No tiene permiso para consultar los permisos del sistema.'
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
            'resumen': [
                indicador(len(catalogo_plano()), 'Permisos del sistema', 'verde', 'llave'),
                indicador(len({g for _, _, g in catalogo_plano()}), 'Módulos', 'azul', 'cuadricula'),
                indicador(Perfiles.objects.filter(Estado_perfil=True).count(), 'Perfiles activos', 'ambar', 'escudo'),
            ],
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
            'activo': 'mi_perfil',
        }
    )


# ============================================================
# PRODUCTOS
# ============================================================

UNIDADES_VALIDAS = ('kg', 'g', 'litros')


def _leer_datos_producto(request, estado_por_defecto, unidad_actual=None,
                         producto_actual=None):
    """Lee y valida los datos del producto y su subtipo.

    Al editar (producto_actual), se permite conservar el tipo y los
    proveedores que el producto ya tenía aunque hoy estén inactivos:
    lo inactivo no se asigna de nuevo, pero tampoco se borra del
    registro histórico.
    """

    tipo_id = request.POST.get('ID_Tipo_producto', '').strip()
    subtipo_id = request.POST.get('ID_Subtipo', '').strip()
    unidad_medida = request.POST.get('Unidad_medida_producto', '').strip()
    estado_producto = request.POST.get(
        'Estado_producto', estado_por_defecto
    ).strip()

    # --------------------------------------------------------
    # TIPO
    # --------------------------------------------------------

    if not tipo_id.isdigit():
        return None, 'Debe seleccionar un tipo de producto.'

    tipo = get_object_or_404(TiposProductos, ID_Tipo_producto=tipo_id)

    conserva_tipo = (
        producto_actual is not None
        and tipo.pk == producto_actual.ID_Tipo_producto_id
    )

    if not tipo.Estado_tipo_producto and not conserva_tipo:
        return None, 'No se pueden registrar productos con un tipo inactivo.'

    # --------------------------------------------------------
    # SUBTIPO
    # --------------------------------------------------------

    if subtipo_id and not subtipo_id.isdigit():
        return None, 'El subtipo seleccionado no es válido.'

    subtipos_disponibles = Subtipos.objects.filter(ID_Tipo_producto=tipo)
    subtipo = None

    if subtipos_disponibles.exists():

        if not subtipo_id:
            return None, (
                'Debe seleccionar un subtipo para este tipo de producto.'
            )

        subtipo = subtipos_disponibles.filter(ID_Subtipo=subtipo_id).first()

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
    # TEXTOS
    # --------------------------------------------------------

    nombre, error = validar_nombre(
        request.POST.get('Nombre_producto', ''),
        'Nombre del producto', 2, 50
    )
    if error:
        return None, error

    descripcion, error = validar_texto(
        request.POST.get('Descripcion_producto', ''),
        'Descripción', maximo=200, obligatorio=False
    )
    if error:
        return None, error

    # --------------------------------------------------------
    # NÚMEROS
    # --------------------------------------------------------

    precio, error = validar_decimal(
        request.POST.get('Precio', ''), 'Precio',
        Decimal('0.01'), Decimal('99999999.99')
    )
    if error:
        return None, error

    cantidad_presentacion, error = validar_decimal(
        request.POST.get('Cantidad_presentacion', ''),
        'Cantidad de presentación',
        Decimal('0.01'), Decimal('99999.99')
    )
    if error:
        return None, error

    unidades_texto = request.POST.get('Unidades_por_presentacion', '').strip()

    if unidades_texto:
        unidades_por_presentacion, error = validar_entero(
            unidades_texto, 'Unidades por presentación', 1, 9999
        )
        if error:
            return None, error
    else:
        unidades_por_presentacion = 1

    stock_minimo, error = validar_entero(
        request.POST.get('Stock_minimo', ''), 'Stock mínimo',
        0, 999999, obligatorio=False
    )
    if error:
        return None, error

    # --------------------------------------------------------
    # UNIDAD DE MEDIDA
    # --------------------------------------------------------

    if not unidad_medida:
        return None, 'Seleccione la unidad de medida.'

    if unidad_medida not in UNIDADES_VALIDAS and unidad_medida != unidad_actual:
        return None, 'La unidad de medida seleccionada no es válida.'

    # --------------------------------------------------------
    # PROVEEDORES QUE SUMINISTRAN EL PRODUCTO
    # --------------------------------------------------------

    ids_proveedores = {
        i.strip()
        for i in request.POST.getlist('proveedores')
        if i.strip().isdigit()
    }

    # Activos, o inactivos que el producto ya tenía asignados.
    permitidos = Q(estado_proveedor=True)

    if producto_actual is not None:
        permitidos |= Q(
            ID_Proveedor__in=producto_actual.proveedores.values('ID_Proveedor')
        )

    proveedores_producto = list(
        Proveedores.objects.filter(
            permitidos,
            ID_Proveedor__in=ids_proveedores
        ).distinct()
    )

    if not proveedores_producto:
        return None, 'Seleccione al menos un proveedor que suministre el producto.'

    if len(proveedores_producto) != len(ids_proveedores):
        return None, 'Alguno de los proveedores seleccionados no existe o está inactivo.'

    # --------------------------------------------------------
    # ESTADO
    # --------------------------------------------------------

    if estado_producto not in ('Activo', 'Inactivo'):
        return None, 'El estado del producto no es válido.'

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
        'unidad_medida': unidad_medida,
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


# ============================================================
# FOTO DEL PRODUCTO
# La foto se valida, se gira según la cámara, se achica a
# 1200 px como máximo y se guarda en WEBP: pesa poco y se ve bien.
# ============================================================

IMAGEN_MAX_MB = 5
IMAGEN_TIPOS = ('image/jpeg', 'image/png', 'image/webp')


def _procesar_imagen(archivo):
    """Devuelve (ContentFile, None) si la foto es válida, o (None, error)."""

    if archivo.size > IMAGEN_MAX_MB * 1024 * 1024:
        return None, f'La imagen no puede superar los {IMAGEN_MAX_MB} MB.'

    if (archivo.content_type or '').lower() not in IMAGEN_TIPOS:
        return None, 'La imagen debe ser JPG, PNG o WEBP.'

    try:
        # verify() detecta archivos dañados o que no son imágenes.
        Image.open(archivo).verify()
        archivo.seek(0)

        imagen = ImageOps.exif_transpose(Image.open(archivo))

        if imagen.mode not in ('RGB', 'RGBA'):
            imagen = imagen.convert(
                'RGBA' if 'A' in imagen.getbands() else 'RGB'
            )

        imagen.thumbnail((1200, 1200))

        buffer = BytesIO()
        imagen.save(buffer, format='WEBP', quality=85)

    except (UnidentifiedImageError, OSError, ValueError):
        return None, 'El archivo elegido no es una imagen válida.'

    return ContentFile(buffer.getvalue(), name=f'{uuid.uuid4().hex}.webp'), None


def _leer_imagen(request):
    """Lee la foto del formulario. Devuelve (ContentFile o None, error)."""

    archivo = request.FILES.get('Imagen_producto')

    if not archivo:
        return None, None

    return _procesar_imagen(archivo)


def _borrar_imagen_al_confirmar(nombre):
    """Borra el archivo de la foto vieja, solo si la operación se guardó."""

    if nombre:
        transaction.on_commit(lambda: default_storage.delete(nombre))


def _snapshot_producto(producto, stock=None):
    """Datos del producto para la auditoría.

    La foto se guarda como nombre de archivo (texto): el objeto de
    imagen de Django no se puede guardar en el registro de auditoría.
    """

    datos = snapshot(producto)
    datos['Imagen_producto'] = producto.Imagen_producto.name or 'Sin foto'

    if stock:
        datos['Stock_minimo'] = stock.Stock_minimo

    return datos


def gestion_productos(request):
    """Lista, busca y filtra productos por tipo y subtipo."""

    usuario = usuario_con_acceso(request, 'productos')

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para consultar productos.'
        )
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()
    tipo_id = request.GET.get('tipo', '').strip()

    # Un valor que no es número (URL modificada a mano) se ignora.
    if not tipo_id.isdigit():
        tipo_id = ''


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

    # Todos los tipos (incluidos los inactivos) para el filtro de
    # búsqueda: así se siguen consultando los registros históricos.
    tipos_productos = TiposProductos.objects.order_by(
        'Nombre_tipo_producto'
    )

    # Solo tipos activos para los modales de registrar/editar:
    # un tipo inactivo no puede asignarse a productos.
    tipos_activos = tipos_productos.filter(Estado_tipo_producto=True)

    # Todos los subtipos: el modal de edición necesita los del tipo
    # actual del producto aunque ese tipo esté inactivo. El modal de
    # registrar solo muestra los del tipo elegido (siempre activo).
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
            'tipos_activos': tipos_activos,
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
            # Edición: todos, los inactivos solo se muestran si el
            # producto ya los tenía asignados.
            'proveedores_todos': Proveedores.objects.order_by(
                'nombre_proveedor'
            ),
            'puede_egresar': puede_egresar,
            'datos_egreso': _datos_egreso() if puede_egresar else [],
        }
    )

def crear_producto(request):
    """Registra un producto con su tipo, subtipo y foto (opcional)."""

    usuario = usuario_con_acceso(
        request,
        'productos',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para gestionar productos.'
        )
        return redirect('panel_principal')

    if request.method != 'POST':
        return redirect('gestion_productos')

    # Leer y validar los datos del producto nuevo.
    datos, error = _leer_datos_producto(
        request,
        estado_por_defecto='Activo'
    )

    if error:
        messages.error(request, error)
        return redirect('gestion_productos')

    # Procesar imagen opcional.
    imagen, error = _leer_imagen(request)

    if error:
        messages.error(request, error)
        return redirect('gestion_productos')

    # Comprobar si ya existe un producto con la misma presentación.
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

        # Crear producto.
        producto = Productos(
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

        if imagen:
            producto.Imagen_producto.save(
                imagen.name,
                imagen,
                save=False
            )

        producto.save()

        # Asociar proveedores al producto.
        producto.proveedores.set(datos['proveedores'])

        # El stock inicial es cero.
        # Las entradas se registran mediante lotes.
        stock, _ = Stock.objects.get_or_create(
            ID_Producto=producto,
            defaults={
                'Cantidad_stock': 0,
                'Stock_minimo': datos['stock_minimo'] or 0,
            }
        )

        # Registrar auditoría.
        registrar_auditoria(
            usuario=usuario,
            entidad='Productos',
            objeto=producto,
            accion='CREACION',
            antes={},
            despues=_snapshot_producto(producto, stock),
        )

    messages.success(
        request,
        'Producto registrado correctamente.'
    )

    return redirect('gestion_productos')


def editar_producto(request, pk):
    """Actualiza los datos del producto, su subtipo y su foto."""

    usuario = usuario_con_acceso(
        request,
        'productos',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para gestionar productos.'
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
    antes = _snapshot_producto(producto, stock_previo)

    datos, error = _leer_datos_producto(
        request,
        producto.Estado_producto,
        producto_actual=producto
    )

    if error:
        messages.error(request, error)
        return redirect('gestion_productos')

    imagen, error = _leer_imagen(request)

    if error:
        messages.error(request, error)
        return redirect('gestion_productos')

    quitar_imagen = request.POST.get('quitar_imagen') == '1'

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

        # FOTO: nueva, quitada o sin cambios.
        imagen_vieja = producto.Imagen_producto.name

        if imagen:
            producto.Imagen_producto.save(imagen.name, imagen, save=False)
            _borrar_imagen_al_confirmar(imagen_vieja)

        elif quitar_imagen and imagen_vieja:
            producto.Imagen_producto = None
            _borrar_imagen_al_confirmar(imagen_vieja)

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
        despues = _snapshot_producto(
            producto,
            Stock.objects.filter(ID_Producto=producto).first()
        )

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
            f'{stock.Cantidad_stock} unidades en stock. Puede cambiar su estado a Inactivo.'
        )
        return redirect('gestion_productos')

    try:
        with transaction.atomic():
            imagen = producto.Imagen_producto.name

            # Registrar la eliminación en la auditoría.
            registrar_auditoria(
                usuario=usuario,
                entidad='Productos',
                objeto=producto,
                accion='ELIMINACION',
                antes=_snapshot_producto(producto, stock),
                despues={},
            )

            # Eliminar el producto.
            producto.delete()

            # El archivo de la foto se borra recién cuando se confirma.
            _borrar_imagen_al_confirmar(imagen)

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


def _resumen_lotes(hoy):
    """Indicadores de Lotes (mismo criterio que Lotes.estado_actual)."""
    con_stock = Lotes.objects.exclude(
        ID_Remito__Estado_remito='Anulado'
    ).filter(Cantidad_actual__gt=0)

    return [
        indicador(Lotes.objects.count(), 'Lotes registrados', 'verde', 'caja'),
        indicador(con_stock.filter(Fecha_vencimiento__gte=hoy).count(), 'Vigentes con stock', 'azul', 'check'),
        indicador(
            con_stock.filter(
                Fecha_vencimiento__gte=hoy,
                Fecha_vencimiento__lte=hoy + timedelta(days=config('dias_aviso_vencimiento'))
            ).count(),
            f'Vencen en {config('dias_aviso_vencimiento')} días', 'ambar', 'reloj'
        ),
        indicador(con_stock.filter(Fecha_vencimiento__lt=hoy).count(), 'Vencidos con stock', 'rojo', 'alerta'),
    ]


def registrar_ingreso_lote(request):
    """Consulta de lotes. El alta se hace desde Remitos."""

    usuario = usuario_con_acceso(request, 'lotes')

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para consultar lotes.'
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

    pagina = paginar(request, lotes)

    return render(
        request,
        'inventario/registrar_ingreso_lote.html',
        {
            'usuario': usuario,
            'lotes': pagina,
            'pagina': pagina,
            'proveedores': proveedores,
            'busqueda': busqueda,
            'proveedor_filtro': proveedor_filtro,
            'hoy': hoy,
            'limite': hoy + timedelta(days=config('dias_aviso_vencimiento')),
            'resumen': _resumen_lotes(hoy),
        }
    )

@transaction.atomic
def baja_lote_vencido(request, id_lote):

    usuario = usuario_con_acceso(request, 'egresos', gestionar=True)

    if not usuario:
        messages.error(request, "No tiene permisos para realizar esta operación.")
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

    # Observación opcional de la ventana (ej.: "Devuelto al proveedor").
    observacion, error = validar_texto(
        request.POST.get('observacion', ''), 'Observación',
        maximo=200, obligatorio=False
    )

    if error:
        messages.error(request, error)
        return redirect('registrar_ingreso_lote')

    if observacion:
        detalle = f'{detalle}. {observacion}'

    # Registrar movimiento de stock
    movimiento = MovimientosStock.objects.create(
        ID_Usuario=usuario,
        ID_Tipo_movimiento=tipo_movimiento,
        ID_Lote=lote,
        Cantidad_movimiento_stock=cantidad,
        Observaciones=detalle[:255]
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

    # La alerta de vencimiento de este lote ya quedó resuelta.
    Alertas.objects.filter(
        Tipo_alerta='Vencimiento',
        Atendida=False,
        Mensaje__contains=f'[LOTE_ID:{lote.ID_Lote}]',
    ).update(
        Atendida=True,
        ID_Usuario=usuario,
        Fecha_hora_atencion=timezone.now(),
    )

    # Si el producto quedó en su stock mínimo, se genera esa alerta.
    revisar_stock(stock, usuario)

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
            'No tiene permiso para consultar movimientos de stock.'
        )
        return redirect('panel_principal')

    busqueda = request.GET.get('q', '').strip()
    tipo_sel = request.GET.get('tipo', '').strip()

    # Un valor que no es número (URL modificada a mano) se ignora.
    if not tipo_sel.isdigit():
        tipo_sel = ''

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

    # Cada usuario ve solo sus movimientos; el administrador ve todos.
    movimientos = movimientos_visibles(movimientos, usuario)

    

    # Resumen sobre todos los movimientos que puede ver (sin filtros).
    por_tipo = dict(
        movimientos.order_by()
        .values('ID_Tipo_movimiento__Nombre_tipo_movimiento')
        .annotate(c=Count('pk'))
        .values_list('ID_Tipo_movimiento__Nombre_tipo_movimiento', 'c')
    )
    resumen = [
        indicador(por_tipo.get('Entrada de lote', 0), 'Ingresos de lote', 'verde', 'entrada'),
        indicador(por_tipo.get(TIPO_EGRESO, 0), 'Egresos por venta', 'azul', 'salida'),
        indicador(por_tipo.get('Salida por vencimiento de producto', 0), 'Egresos por vencimiento', 'ambar', 'reloj'),
        indicador(
            por_tipo.get(TIPO_ANULACION_REMITO, 0) + por_tipo.get(TIPO_ANULACION_EGRESO, 0),
            'Anulaciones', 'rojo', 'deshacer'
        ),
    ]

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

    pagina = paginar(request, movimientos)

    return render(
        request,
        'inventario/movimientos_stock.html',
        {
            'movimientos': pagina,
            'pagina': pagina,
            'todos_tipos': todos_tipos,
            'busqueda': busqueda,
            'tipo_sel': tipo_sel,
            'usuario': usuario,
            'activo': 'movimientos',
            'puede_anular': puede_accion(usuario, 'anular_egresos'),
            'resumen': resumen,
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
            'No tiene permiso para consultar el historial de alertas.'
        )
        return redirect('panel_principal')

    es_admin = usuario.ID_Perfil.Nombre_perfil in PERFILES_ADMIN

    tipo_alerta = request.GET.get('tipo', '').strip()
    producto_id = request.GET.get('producto', '').strip()
    usuario_id = request.GET.get('usuario', '').strip()
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()

    generar_alertas_vencimiento()

    # Base: solo las alertas que este usuario puede ver.
    # Las tarjetas de arriba se cuentan sobre esta misma base.
    visibles = alertas_visibles(usuario)
    alertas_bd = visibles

    if tipo_alerta == TIPO_STOCK:
        alertas_bd = alertas_bd.filter(Tipo_alerta__in=TIPOS_STOCK)
    elif tipo_alerta:
        alertas_bd = alertas_bd.filter(Tipo_alerta=tipo_alerta)

    if producto_id.isdigit():
        alertas_bd = alertas_bd.filter(ID_Stock__ID_Producto_id=producto_id)

    if usuario_id.isdigit():
        alertas_bd = alertas_bd.filter(ID_Usuario_id=usuario_id)

    # Fechas inválidas en la URL se ignoran (antes daban error 500).
    desde = _fecha_iso(fecha_desde)
    hasta = _fecha_iso(fecha_hasta)

    if desde:
        alertas_bd = alertas_bd.filter(Fecha_hora_historial_alerta__date__gte=desde)
    if hasta:
        alertas_bd = alertas_bd.filter(Fecha_hora_historial_alerta__date__lte=hasta)

    alertas_bd = list(alertas_bd.order_by('-Fecha_hora_historial_alerta'))

    # Lotes de las alertas de vencimiento: una sola consulta para todos
    # (antes se hacía una consulta por cada alerta).
    def _lote_id(mensaje):
        try:
            return int(mensaje.rsplit('[LOTE_ID:', 1)[1].split(']', 1)[0])
        except (IndexError, ValueError):
            return None

    ids_lotes = {
        _lote_id(a.Mensaje) for a in alertas_bd
        if a.Tipo_alerta == 'Vencimiento'
    } - {None}

    lotes = Lotes.objects.in_bulk(ids_lotes)

    alertas = []

    for alerta in alertas_bd:
        lote = None
        mensaje = alerta.Mensaje

        if alerta.Tipo_alerta == 'Vencimiento':
            lote = lotes.get(_lote_id(mensaje))
            # Quita el identificador técnico del mensaje visible.
            mensaje = mensaje_visible(mensaje)

        alertas.append({
            'id': alerta.ID_Historial_alerta,
            'tipo': (
                TIPO_STOCK if alerta.Tipo_alerta in TIPOS_STOCK
                else alerta.Tipo_alerta
            ),
            'producto': alerta.ID_Stock.ID_Producto,
            'lote': lote,
            'mensaje': mensaje,
            'fecha': alerta.Fecha_hora_historial_alerta,
            'cantidad': alerta.Cantidad_al_generar,
            'stock_minimo': alerta.Stock_minimo_al_generar,
            'atendida': alerta.Atendida,
            'usuario': alerta.ID_Usuario,
            'fecha_atencion': alerta.Fecha_hora_atencion,
        })

    # Filtro de búsqueda: todos los productos, incluidos los inactivos,
    # porque sus alertas siguen formando parte del historial.
    productos = Productos.objects.order_by('Nombre_producto')

    # Filtro "Atendida por": el administrador elige entre todos;
    # el resto solo puede elegirse a sí mismo.
    # Se incluyen los usuarios inactivos porque las alertas que
    # atendieron siguen formando parte del historial.
    if es_admin:
        usuarios = Usuarios.objects.order_by(
            'Apellido_usuario', 'Nombre_usuario'
        )
    else:
        usuarios = Usuarios.objects.filter(ID_Usuario=usuario.ID_Usuario)

    pagina = paginar(request, alertas)

    pendientes = visibles.filter(Atendida=False)

    return render(
        request,
        'inventario/historial_alertas.html',
        {
            'alertas': pagina,
            'pagina': pagina,
            'tipo_alerta': tipo_alerta,
            'producto_id': producto_id,
            'usuario_id': usuario_id,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'productos': productos,
            'usuarios': usuarios,
            'usuario': usuario,
            'es_admin': es_admin,
            'resumen': [
                indicador(pendientes.count(), 'Sin atender', 'rojo', 'alerta'),
                indicador(
                    pendientes.filter(Tipo_alerta__in=TIPOS_STOCK).count(),
                    'Stock mínimo sin atender', 'ambar', 'bajada'
                ),
                indicador(
                    pendientes.filter(Tipo_alerta='Vencimiento').count(),
                    'Vencimientos sin atender', 'azul', 'reloj'
                ),
                indicador(
                    visibles.filter(Atendida=True).count(),
                    'Atendidas' if es_admin else 'Atendidas por mí',
                    'verde', 'check'
                ),
            ],
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
                {'ok': False, 'error': 'No tiene permiso para atender alertas.'},
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
            {'error': 'No tiene permiso para ver las alertas.'},
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
            'No tiene permiso para emitir comprobantes.'
        )
        return redirect('panel_principal')

    movimiento = get_object_or_404(
        movimientos_visibles(
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
            usuario
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
            'No tiene permiso para consultar remitos.'
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

TOTAL_LOTE_MAX = 10_000_000   # cajas x unidades por caja


def _validar_numero_y_fecha_remito(numero_texto, fecha_texto, hoy):
    """Valida el número y la fecha de un remito. Devuelve (numero, fecha, error)."""

    numero, error = validar_codigo(
        numero_texto, 'Número de remito', 3, 20
    )

    if error:
        return None, None, error

    fecha, error = validar_fecha(
        fecha_texto, 'Fecha del remito',
        desde=hoy - timedelta(days=3650),
        hasta=hoy,
        msg_desde='La fecha del remito es demasiado antigua (máximo 10 años).',
        msg_hasta='La fecha del remito no puede ser futura.'
    )

    if error:
        return None, None, error

    return numero, fecha, None


def _remito_duplicado(numero, excluir_id=None):
    """Mensaje de error si ya hay un remito con ese número (sin importar
    mayúsculas ni el proveedor); None si el número está libre."""
    existentes = Remitos.objects.filter(Numero_remito__iexact=numero)

    if excluir_id:
        existentes = existentes.exclude(ID_Remito=excluir_id)

    existente = existentes.select_related('ID_Proveedor').first()

    if not existente:
        return None

    return (
        f'Ya existe un remito con el número "{existente.Numero_remito}" '
        f'(proveedor {existente.ID_Proveedor.nombre_proveedor}). '
        'Verifique el número ingresado.'
    )


def _validar_lote(numero_texto, cajas_texto, unidades_texto,
                  vencimiento_texto, hoy, permitir_vencido=False):
    """Valida los datos de un lote. Devuelve (datos, error)."""

    numero, error = validar_codigo(numero_texto, 'Número de lote', 1, 50)
    if error:
        return None, error

    cajas, error = validar_entero(
        cajas_texto, 'Cantidad de cajas', 1, 999999
    )
    if error:
        return None, error

    unidades, error = validar_entero(
        unidades_texto, 'Unidades por caja', 1, 999999
    )
    if error:
        return None, error

    if cajas * unidades > TOTAL_LOTE_MAX:
        return None, (
            'Un lote no puede superar las 10.000.000 unidades '
            '(cajas × unidades por caja).'
        )

    vencimiento, error = validar_fecha(
        vencimiento_texto, 'Fecha de vencimiento',
        desde=None if permitir_vencido else hoy,
        hasta=hoy + timedelta(days=5475),
        msg_desde='No se pueden registrar lotes ya vencidos.',
        msg_hasta='La fecha de vencimiento no puede superar los 15 años.'
    )
    if error:
        return None, error

    return {
        'numero': numero,
        'cajas': cajas,
        'unidades_caja': unidades,
        'vencimiento': vencimiento,
        'cantidad': cajas * unidades,
    }, None

def gestion_remitos(request):
    usuario = usuario_con_acceso(
        request,
        'remitos',
        gestionar=(request.method == 'POST')
    )

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para esta operación sobre remitos.'
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

            productos_ids = request.POST.getlist('lote_producto')
            numeros_lote = request.POST.getlist('lote_numero')
            vencimientos = request.POST.getlist('lote_vencimiento')
            cajas_lista = request.POST.getlist('lote_cajas')
            unidades_lista = request.POST.getlist('lote_unidades_caja')

            if not proveedor_id.isdigit():
                messages.error(request, 'Seleccione un proveedor.')
                return redirect('gestion_remitos')

            numero_remito, fecha_remito, error = _validar_numero_y_fecha_remito(
                request.POST.get('Numero_remito', ''),
                request.POST.get('Fecha_remito', ''),
                hoy
            )

            if not error:
                error = _remito_duplicado(numero_remito)

            if error:
                messages.error(request, error)
                return redirect('gestion_remitos')

            if not (
                len(productos_ids) == len(numeros_lote)
                == len(vencimientos) == len(cajas_lista)
                == len(unidades_lista)
            ) or not productos_ids:
                messages.error(
                    request,
                    'Agregue al menos un lote y complete todos sus datos.'
                )
                return redirect('gestion_remitos')

            if len(productos_ids) > 50:
                messages.error(
                    request,
                    'Un remito no puede tener más de 50 lotes.'
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
                if not producto_id.strip().isdigit():
                    messages.error(
                        request,
                        'Seleccione el producto de cada lote.'
                    )
                    return redirect('gestion_remitos')

                datos_lote, error = _validar_lote(
                    numero_lote, cajas_texto, unidades_texto,
                    vencimiento_texto, hoy
                )

                if error:
                    messages.error(request, error)
                    return redirect('gestion_remitos')

                if datos_lote['vencimiento'] < fecha_remito:
                    messages.error(
                        request,
                        'La fecha de vencimiento no puede ser anterior '
                        'a la fecha del remito.'
                    )
                    return redirect('gestion_remitos')

                producto = Productos.objects.filter(
                    ID_Producto=producto_id.strip(),
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
                if not producto.proveedores.filter(pk=proveedor.pk).exists():
                    messages.error(
                        request,
                        f'El producto "{producto.Nombre_producto}" no es '
                        f'suministrado por el proveedor '
                        f'"{proveedor.nombre_proveedor}".'
                    )
                    return redirect('gestion_remitos')

                numero_lote = datos_lote['numero']

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
                        'No puede repetir el número de lote para el mismo producto.'
                    )
                    return redirect('gestion_remitos')

                combinaciones.add(combinacion)

                lotes_validados.append({
                    'producto': producto,
                    'numero': numero_lote,
                    'vencimiento': datos_lote['vencimiento'],
                    'cajas': datos_lote['cajas'],
                    'unidades_caja': datos_lote['unidades_caja'],
                    'cantidad': datos_lote['cantidad'],
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
                        usuario, 'Lotes', lote, 'INGRESO_LOTE', {}, dict(snapshot(lote),
                        Stock_antes=stock_antes,
                        Stock_despues=stock.Cantidad_stock))
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

            numero_remito, fecha_remito, error = _validar_numero_y_fecha_remito(
                request.POST.get('Numero_remito', ''),
                request.POST.get('Fecha_remito', ''),
                hoy
            )

            if not remito_id.isdigit():
                error = error or 'El remito seleccionado no es válido.'

            if not error:
                error = _remito_duplicado(numero_remito, excluir_id=remito_id)

            if error:
                messages.error(request, error)
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
                    'Ya existe otro remito con ese número.'
                )

            return redirect('gestion_remitos')
        
       
      
        # ====================================================
        # EDITAR DATOS DEL LOTE
        # ====================================================
        # ====================================================
        
        elif accion == 'editar_lote':

            lote_id = request.POST.get('ID_Lote', '').strip()
            

            if not lote_id.isdigit():
                messages.error(request, 'El lote seleccionado no es válido.')
                return redirect('gestion_remitos')

            numero_lote, error = validar_codigo(
                request.POST.get('Numero_lote', ''), 'Número de lote', 1, 50
            )

            if not error:
                cajas, error = validar_entero(
                    request.POST.get('Cantidad_cajas', ''),
                    'Cantidad de cajas', 1, 999999
                )

            if not error:
                unidades_caja, error = validar_entero(
                    request.POST.get('Unidades_por_caja', ''),
                    'Unidades por caja', 1, 999999
                )

            if not error and cajas * unidades_caja > TOTAL_LOTE_MAX:
                error = (
                    'Un lote no puede superar las 10.000.000 unidades '
                    '(cajas × unidades por caja).'
                )

            if error:
                messages.error(request, error)
                return redirect('gestion_remitos')

            cantidad_ingresada = cajas * unidades_caja

            try:
                with transaction.atomic():
                    lote = Lotes.objects.select_for_update().select_related(
                        'ID_Producto', 'ID_Remito'
                    ).get(ID_Lote=lote_id)

                    # ---------- LOTES QUE NO SE PUEDEN EDITAR ----------
                    if lote.ID_Remito.Estado_remito == 'Anulado':
                        messages.error(
                            request,
                            'No se puede modificar un lote de un remito anulado.'
                        )
                        return redirect('gestion_remitos')

                    if lote.Cantidad_actual <= 0:
                        messages.error(
                            request,
                            'No se puede modificar un lote agotado: '
                            'queda como registro histórico.'
                        )
                        return redirect('gestion_remitos')

                    # ---------- VENCIMIENTO ----------
                    fecha_vencimiento, error = validar_fecha(
                        request.POST.get('Fecha_vencimiento', ''),
                        'Fecha de vencimiento',
                        desde=lote.ID_Remito.Fecha_remito,
                        hasta=hoy + timedelta(days=5475),
                        msg_desde=(
                            'La fecha de vencimiento no puede ser anterior '
                            'a la fecha del remito.'
                        ),
                        msg_hasta='La fecha de vencimiento no puede superar los 15 años.'
                    )

                    if error:
                        messages.error(request, error)
                        return redirect('gestion_remitos')

                    # ---------- NÚMERO DE LOTE REPETIDO ----------
                    if Lotes.objects.filter(
                        ID_Producto=lote.ID_Producto,
                        Numero_lote=numero_lote
                    ).exclude(ID_Lote=lote.ID_Lote).exists():
                        messages.error(
                            request,
                            'Ya existe ese número de lote para el producto.'
                        )
                        return redirect('gestion_remitos')

                    # ---------- CAJAS Y UNIDADES ----------
                    tipo_entrada = TiposMovimientos.objects.filter(
                        Nombre_tipo_movimiento__iexact='Entrada de lote'
                    ).first()

                    entrada = MovimientosStock.objects.select_for_update().filter(
                        ID_Lote=lote,
                        ID_Tipo_movimiento=tipo_entrada
                    ).first() if tipo_entrada else None

                    # Salidas: cualquier movimiento que no sea la entrada,
                    # o una cantidad actual distinta de la ingresada.
                    otros_movimientos = MovimientosStock.objects.filter(
                        ID_Lote=lote
                    ).exclude(
                        ID_Movimiento_stock=entrada.ID_Movimiento_stock if entrada else None
                    ).exists()

                    tuvo_salidas = (
                        otros_movimientos
                        or lote.Cantidad_actual != lote.Cantidad_ingresada
                    )

                    # Lotes viejos sin cajas guardadas: se compara el total.
                    if lote.Cantidad_cajas is None or lote.Unidades_por_caja is None:
                        cambio_cajas = cantidad_ingresada != lote.Cantidad_ingresada
                    else:
                        cambio_cajas = (
                            cajas != lote.Cantidad_cajas
                            or unidades_caja != lote.Unidades_por_caja
                        )

                    if cambio_cajas and tuvo_salidas:
                        messages.error(
                            request,
                            'No se pueden cambiar las cajas ni las unidades '
                            'porque el lote ya tuvo salidas.'
                        )
                        return redirect('gestion_remitos')

                    cambio_total = cantidad_ingresada != lote.Cantidad_ingresada

                    if (
                        lote.Numero_lote == numero_lote
                        and lote.Fecha_vencimiento == fecha_vencimiento
                        and not cambio_cajas
                    ):
                        messages.info(
                            request,
                            'No se realizaron cambios en el lote.'
                        )
                        return redirect('gestion_remitos')

                    antes = snapshot(lote)

                    # Si cambia el total, se corrige el stock y la entrada.
                    if cambio_total:
                        if not entrada:
                            messages.error(
                                request,
                                'No se encontró el movimiento de entrada del lote.'
                            )
                            return redirect('gestion_remitos')

                        diferencia = cantidad_ingresada - lote.Cantidad_ingresada

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

                        entrada.Cantidad_movimiento_stock = cantidad_ingresada
                        entrada.save(update_fields=['Cantidad_movimiento_stock'])

                        # El lote está intacto: su cantidad actual es el total.
                        lote.Cantidad_actual = cantidad_ingresada

                    lote.Numero_lote = numero_lote
                    lote.Cantidad_cajas = cajas
                    lote.Unidades_por_caja = unidades_caja
                    lote.Cantidad_ingresada = cantidad_ingresada
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
            motivo, error = validar_texto(
                request.POST.get('Motivo_anulacion', ''),
                'Justificación', minimo=10, maximo=200, obligatorio=True
            )

            if error:
                messages.error(request, error)
                return redirect('gestion_remitos')

            if not remito_id.isdigit():
                messages.error(request, 'El remito seleccionado no es válido.')
                return redirect('gestion_remitos')

            if not puede_accion(usuario, 'anular_remitos'):
                messages.error(
                    request,
                    'No tiene permiso para anular remitos.'
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
                    for l in lotes_remito)

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

    # Filtro por rango de fechas del remito
    texto_desde = request.GET.get('desde', '').strip()
    texto_hasta = request.GET.get('hasta', '').strip()
    fecha_desde = _fecha_iso(texto_desde) if texto_desde else None
    fecha_hasta = _fecha_iso(texto_hasta) if texto_hasta else None

    if texto_desde and not fecha_desde:
        messages.error(request, 'La fecha "Desde" no es válida.')
    if texto_hasta and not fecha_hasta:
        messages.error(request, 'La fecha "Hasta" no es válida.')

    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        messages.error(request, 'La fecha "Desde" no puede ser posterior a "Hasta".')
    else:
        if fecha_desde:
            remitos = remitos.filter(Fecha_remito__gte=fecha_desde)
        if fecha_hasta:
            remitos = remitos.filter(Fecha_remito__lte=fecha_hasta)

    if busqueda:
        remitos = remitos.filter(
            Q(Numero_remito__icontains=busqueda)
            | Q(ID_Proveedor__nombre_proveedor__icontains=busqueda)
        )

    if proveedor_filtro.isdigit():
        remitos = remitos.filter(
            ID_Proveedor__ID_Proveedor=proveedor_filtro
        )
    else:
        proveedor_filtro = ''

    # Filtro de búsqueda: todos los proveedores con remitos, incluidos
    # los inactivos, para consultar sus registros históricos.
    proveedores = Proveedores.objects.filter(
        remitos__isnull=False
    ).distinct().order_by('nombre_proveedor')

    # Modal de alta: solo proveedores activos.
    proveedores_alta = Proveedores.objects.filter(
        estado_proveedor=True
    ).order_by('nombre_proveedor')

    productos_alta = Productos.objects.filter(
        Estado_producto='Activo'
    ).prefetch_related(
        'proveedores'
    ).order_by('Nombre_producto')

    pagina = paginar(request, remitos)

    return render(
        request,
        'inventario/gestion_remitos.html',
        {
            'usuario': usuario,
            'remitos': pagina,
            'pagina': pagina,
            'proveedores': proveedores,
            'proveedores_alta': proveedores_alta,
            'productos_alta': productos_alta,
            'total_remitos': Remitos.objects.count(),
            'total_proveedores': Remitos.objects.values(
                'ID_Proveedor'
            ).distinct().count(),
            'total_lotes': Lotes.objects.count(),
            'resumen': [
                indicador(Remitos.objects.count(), 'Remitos registrados', 'verde', 'documento'),
                indicador(
                    Remitos.objects.values('ID_Proveedor').distinct().count(),
                    'Proveedores', 'azul', 'camion'
                ),
                indicador(Lotes.objects.count(), 'Lotes asociados', 'ambar', 'caja'),
                indicador(Remitos.objects.filter(Estado_remito='Anulado').count(), 'Anulados', 'rojo', 'deshacer'),
            ],
            'busqueda': busqueda,
            'proveedor_filtro': proveedor_filtro,
            'estado_filtro': estado_filtro,
            'fecha_desde': texto_desde,
            'fecha_hasta': texto_hasta,
            'puede_anular': puede_accion(usuario, 'anular_remitos'),
            'puede_gestionar': puede(usuario, 'remitos', gestionar=True),
            'hoy': hoy,
            # Para avisar en el modal, mientras se escribe, si el número
            # de remito ya existe (el servidor lo vuelve a controlar).
            'numeros_remito': [
                {'id': r['ID_Remito'], 'numero': r['Numero_remito'],
                 'proveedor': r['ID_Proveedor__nombre_proveedor']}
                for r in Remitos.objects.values(
                    'ID_Remito', 'Numero_remito', 'ID_Proveedor__nombre_proveedor'
                )
            ] if puede(usuario, 'remitos', gestionar=True) else [],
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


def _registro_sin_repetir(log):
    """Nombre del registro afectado, salvo que sea el mismo usuario que
    hizo la acción (inicio/cierre de sesión, bloqueo...): ahí ya figura
    en la columna Usuario y no hace falta repetirlo."""
    nombre = nombre_registro(log)
    u = log.ID_Usuario

    if nombre and u and nombre in (
        f'{u.Apellido_usuario}, {u.Nombre_usuario}',
        f'{u.Apellido_usuario} {u.Nombre_usuario}',
        u.Usuario,
    ):
        return None

    return nombre


def _resumen_auditoria():
    hoy = _inicio_dia(timezone.localdate())
    semana = hoy - timedelta(days=6)
    return [
        indicador(LogAuditoria.objects.count(), 'Registros totales', 'verde', 'documento'),
        indicador(LogAuditoria.objects.filter(Fecha_hora__gte=hoy).count(), 'Registros de hoy', 'azul', 'calendario'),
        indicador(LogAuditoria.objects.filter(Fecha_hora__gte=semana).count(), 'Últimos 7 días', 'ambar', 'actividad'),
        indicador(
            LogAuditoria.objects.filter(Fecha_hora__gte=semana).values('ID_Usuario').distinct().count(),
            'Usuarios con actividad (7 días)', 'rojo', 'usuarios'
        ),
    ]


def gestion_auditoria(request):

    usuario = usuario_con_acceso(request, 'auditoria')

    if not usuario:
        messages.error(
            request,
            'No tiene permiso para consultar la auditoría.'
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

    pagina = paginar(request, logs, por_defecto=25)

    # Nombre del registro afectado (producto, proveedor, usuario...).
    for log in pagina:
        log.nombre_registro = _registro_sin_repetir(log)

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
            'resumen': _resumen_auditoria(),
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
            {'error': 'No tiene permiso para consultar la auditoría.'},
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
        'CREACION', 'EGRESO_STOCK', 'EGRESO_VENCIMIENTO', 'INGRESO_LOTE',
        'DESCARGA_PDF', 'ENVIO_RECUPERACION', 'BLOQUEO_INACTIVIDAD',
        'ATENCION_NOTIFICACION',
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
        'nombre_registro': _registro_sin_repetir(log),
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
            'No tiene permiso para registrar egresos de stock.'
        )
        return redirect('panel_principal')

    lote_id = request.POST.get('lote', '').strip()

    if not lote_id.isdigit():
        messages.error(request, 'Seleccione un lote válido.')
        return redirect('gestion_productos')

    try:
        cantidad, error = validar_entero(
        request.POST.get('cantidad', ''), 'Cantidad', 1, 999999
    )
    except (ValueError, TypeError):
        messages.error(request, 'La cantidad ingresada no es válida.')
        return redirect('gestion_productos')

    if error:
        messages.error(request, error)
        return redirect('gestion_productos')

    descripcion, error = validar_texto(
        request.POST.get('descripcion', ''), 'Descripción',
        maximo=200, obligatorio=False
    )

    lote_base = Lotes.objects.filter(ID_Lote=lote_id).first()

    if not lote_base:
        messages.error(request, 'El lote seleccionado no existe.')
        return redirect('gestion_productos')

    if error:
        messages.error(request, error)
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

            # Regla de 3σ: avisa al Administrador si la cantidad es inusual.
            revisar_egreso_inusual(movimiento)

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
            'No tiene permiso para anular egresos de stock.'
        )
        return redirect('panel_principal')

    motivo, error = validar_texto(
                request.POST.get('Motivo_anulacion', ''),
                'Justificación', minimo=10, maximo=200, obligatorio=True
            )

    if error:
        messages.error(request, error)
        return redirect('gestion_movimientos_stock')   

    tipo_egreso = TiposMovimientos.objects.filter(
        Nombre_tipo_movimiento=TIPO_EGRESO
    ).first()

    hoy = timezone.localdate()

    try:
        with transaction.atomic():

            # 1) Se bloquea el egreso: dos usuarios no pueden anularlo a la vez.
            movimiento = movimientos_visibles(
                MovimientosStock.objects.select_for_update(),
                usuario
            ).get(
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

            # 4) Movimiento de anulación (suma). Sus observaciones indican qué egreso anuló.
            tipo_anulacion, _ = TiposMovimientos.objects.get_or_create(
                Nombre_tipo_movimiento=TIPO_ANULACION_EGRESO
            )

            contramovimiento = MovimientosStock.objects.create(
                ID_Usuario=usuario,
                ID_Tipo_movimiento=tipo_anulacion,
                ID_Lote=lote,

                Cantidad_movimiento_stock=cantidad,
                
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
            'No tiene permiso para consultar los reportes.'
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
            {'error': 'No tiene permiso para consultar los reportes.'},
            status=403
        )

    # Filtros por producto (tipo, subtipo, proveedor). Los valores
    # que no sean números se ignoran.
    filtros = {}

    for campo in ('tipo', 'subtipo', 'proveedor'):
        valor = request.GET.get(campo, '').strip()
        if valor.isdigit():
            filtros[campo + '_id'] = int(valor)

    texto_desde = request.GET.get('desde', '').strip()
    texto_hasta = request.GET.get('hasta', '').strip()

    # Sin fechas: los últimos 12 meses (solo con los filtros).
    if not texto_desde and not texto_hasta:
        return JsonResponse(datos_evolucion_12_meses(TIPO_EGRESO, **filtros))

    desde = _fecha_iso(texto_desde)
    hasta = _fecha_iso(texto_hasta)

    if not desde or not hasta:
        return JsonResponse(
            {'error': 'Las fechas ingresadas no son válidas.'},
            status=400
        )

    # No tiene sentido consultar fechas futuras.
    hasta = min(hasta, timezone.localdate())

    try:
        datos = datos_evolucion_rango(desde, hasta, TIPO_EGRESO, **filtros)
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
            error = 'Ingrese con el mismo usuario de la sesión bloqueada.'

        elif not check_password(password, usuario.Contrasena):
            error = 'Usuario o contraseña incorrectos.'

        else:
            request.session['bloqueada'] = False
            request.session['bloqueo_intentos'] = 0
            request.session['bloqueo_registrado'] = False
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

    # Pantalla de bloqueo: queda registrado que le apareció el aviso.
    if request.method == 'GET':
        request.session['bloqueada'] = True
        registrar_bloqueo_inactividad(request, usuario, siguiente)

    return render(
        request,
        'inventario/bloqueo.html',
        {
            'usuario': usuario,
            'error': error,
            'siguiente': siguiente,
            # Mismo tiempo que settings.INACTIVIDAD_SEGUNDOS (antes decía 15 fijo).
            'minutos_inactividad': getattr(
                settings, 'INACTIVIDAD_SEGUNDOS', 30 * 60
            ) // 60,
        }
    )


@require_POST
def registrar_bloqueo(request):
    """El navegador avisa que mostró el cartel de bloqueo por inactividad."""

    usuario = usuario_autenticado(request)

    if not usuario:
        return JsonResponse({'ok': False}, status=401)

    # La sesión queda bloqueada también en el servidor.
    request.session['bloqueada'] = True

    pantalla = request.POST.get('pantalla', '')[:200]
    registrar_bloqueo_inactividad(request, usuario, pantalla)

    return JsonResponse({'ok': True})


def sesion_ping(request):
    """Mantiene viva la sesión mientras el usuario está activo en pantalla."""

    if not usuario_autenticado(request):
        return JsonResponse({'ok': False}, status=401)

    return JsonResponse({'ok': True})


# Permite 3 solicitudes y bloquea durante 15 minutos.

def limite_superado(request, email):

    ahora = time_module.time()

    # Identifica el correo sin guardar su dirección directamente en la sesión.
    email_hash = hashlib.sha256(
        email.strip().lower().encode()
    ).hexdigest()

    clave = f'recuperacion_{email_hash}'

    datos = request.session.get(clave, {})

    # Comprobar si todavía está vigente el bloqueo.
    bloqueada_hasta = datos.get('bloqueada_hasta', 0)

    if ahora < bloqueada_hasta:
        return True

    # Si el bloqueo venció, comenzar nuevamente.
    if bloqueada_hasta:
        datos = {'intentos': []}

    # Conservar solamente los intentos realizados en los últimos 15 minutos.
    intentos = [
        t for t in datos.get('intentos', [])
        if ahora - t < 15 * 60
    ]

    # Registrar el intento actual.
    intentos.append(ahora)

    datos = {'intentos': intentos}

    # Al llegar al tercer intento, bloquear las siguientes solicitudes.
    if len(intentos) >= 3:
        datos['bloqueada_hasta'] = ahora + (15 * 60)

    request.session[clave] = datos
    request.session.modified = True

    return False


# Devuelve los segundos que faltan para terminar el bloqueo.

def tiempo_bloqueo_restante(request, email):
    
    email_hash = hashlib.sha256(
        email.strip().lower().encode()
    ).hexdigest()

    clave = f'recuperacion_{email_hash}'
    datos = request.session.get(clave, {})

    bloqueada_hasta = datos.get('bloqueada_hasta', 0)

    return max(0, int(bloqueada_hasta - time_module.time()))


# ============================================================
# RECUPERAR CONTRASEÑA (desde el login, sin sesión)
# ============================================================


def recuperar_contrasena(request):

    if request.method != 'POST':
        return render(
            request,
            'inventario/recuperar_contrasena.html'
        )

    email_ingresado = request.POST.get('email', '').strip()
    contexto = {'email': email_ingresado}

    # --------------------------------------------------------
    # VALIDAR CORREO
    # --------------------------------------------------------

    if not email_ingresado:
        error = 'Ingrese su correo electrónico.'
    else:
        email, error = validar_email(email_ingresado, '')

    if error:
        contexto['errores'] = {'email': error}
        return render(
            request,
            'inventario/recuperar_contrasena.html',
            contexto
        )

    # --------------------------------------------------------
    # CONTROLAR LÍMITE DE SOLICITUDES
    # --------------------------------------------------------

    if limite_superado(request, email):
        contexto['error'] = (
            'Hiciste demasiados intentos. '
            'Espere 15 minutos antes de volver a intentarlo.'
        )

        contexto['bloqueo_segundos'] = tiempo_bloqueo_restante(
            request, email
        )

        return render(
            request,
            'inventario/recuperar_contrasena.html',
            contexto
        )

    # --------------------------------------------------------
    # BUSCAR USUARIOS CON ESE CORREO
    # --------------------------------------------------------

    usuarios = list(
        Usuarios.objects.select_related('ID_Perfil').filter(
            Email_usuario__iexact=email
        )
    )

    habilitados = [
        u for u in usuarios
        if usuario_habilitado(u)
    ]

    # --------------------------------------------------------
    # SI EXISTEN USUARIOS HABILITADOS, ENVIAR EL ENLACE
    # --------------------------------------------------------

    if habilitados:

        for u in habilitados:
            enviar_correo_recuperacion(u)

        contexto['enviado'] = True

    # --------------------------------------------------------
    # SI EL USUARIO ESTÁ DADO DE BAJA
    # --------------------------------------------------------

    elif any(not u.Estado_usuario for u in usuarios):

        contexto['error'] = (
            'Su usuario fue dado de baja. '
            'Comuníquese con un administrador.'
        )

    # --------------------------------------------------------
    # SI EL USUARIO NO ESTÁ HABILITADO
    # --------------------------------------------------------

    elif usuarios:

        contexto['error'] = (
            'Su usuario no está habilitado para ingresar. '
            'Comuníquese con un administrador.'
        )

    # --------------------------------------------------------
    # SI EL CORREO NO ESTÁ REGISTRADO
    # --------------------------------------------------------

    else:

        contexto['errores'] = {
            'email': 'El correo electrónico no está registrado.'
        }

    return render(
        request,
        'inventario/recuperar_contrasena.html',
        contexto
    )


def recuperar_confirmar(request, uidb64, token):

    usuario = usuario_desde_uid(uidb64)

    if not usuario_habilitado(usuario) or not token_valido(usuario, token):
        return render(
            request,
            'inventario/recuperar_confirmar.html',
            {'invalido': True}
        )

    contexto = {'usuario_nombre': usuario.Usuario}

    if request.method == 'POST':
        nueva = request.POST.get('nueva_contrasena', '')
        confirmar = request.POST.get('confirmar_contrasena', '')

        errores = _errores_nueva_contrasena(nueva, confirmar, usuario)

        if errores:
            contexto['errores'] = errores
            return render(
                request,
                'inventario/recuperar_confirmar.html',
                contexto
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
            'Su contraseña se cambió correctamente. Ya puede ingresar.'
        )

        return redirect('login')

    return render(request, 'inventario/recuperar_confirmar.html', contexto)
