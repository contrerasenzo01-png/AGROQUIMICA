"""
Vistas del Parcial 2 · Agroquímica del Valle

  M2 - Reportes consolidados (grilla paginada con totales y PDF).
  M3 - Bandeja de notificaciones (JSON del header y pantalla completa)
       y configuración de los umbrales de las reglas de alertas.
"""

from datetime import date

from django.contrib import messages
from django.contrib.staticfiles import finders
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .alertas import revisar_stock, revisar_vencimientos
from .auditoria import registrar_auditoria, snapshot
from .consolidados import REPORTES, fila_totales, filas_formateadas
from .models import (
    Configuracion, LogAuditoria, Notificacion, Proveedores, Stock, TiposProductos,
)
from .notificaciones import (
    PARAMETROS, asegurar_configuracion, datos_bandeja, marcar_leida,
    marcar_todas_leidas, no_leidas, notificaciones_de,
)
from .paginacion import paginar
from .pdf_consolidado import generar_pdf_consolidado
from .permissions import puede_accion, usuario_con_acceso


def _usuario():
    # Import diferido: views.py importa este módulo indirectamente.
    from .views import usuario_autenticado
    return usuario_autenticado


def _fecha(texto):
    try:
        return date.fromisoformat((texto or '').strip())
    except ValueError:
        return None


def _entero(texto):
    texto = (texto or '').strip()
    return int(texto) if texto.isdigit() else None


# ============================================================
# M2 · REPORTES CONSOLIDADOS
# ============================================================

def _reportes_visibles(usuario):
    """Los reportes que el perfil puede ver (el sensible requiere permiso)."""
    ver_sensibles = puede_accion(usuario, 'reportes_sensibles')
    return [
        (clave, r) for clave, r in REPORTES.items()
        if not r['sensible'] or ver_sensibles
    ]


def _leer_filtros(request):
    """Filtros de la URL. Por defecto: desde el 1° de enero hasta hoy."""
    hoy = timezone.localdate()
    errores = []

    desde = _fecha(request.GET.get('desde')) or date(hoy.year, 1, 1)
    hasta = _fecha(request.GET.get('hasta')) or hoy

    if request.GET.get('desde') and not _fecha(request.GET.get('desde')):
        errores.append('La fecha "Desde" no es válida.')
    if request.GET.get('hasta') and not _fecha(request.GET.get('hasta')):
        errores.append('La fecha "Hasta" no es válida.')

    if desde > hasta:
        errores.append('La fecha "Desde" no puede ser posterior a "Hasta".')
        desde, hasta = date(hoy.year, 1, 1), hoy

    tipo = _entero(request.GET.get('tipo'))
    proveedor = _entero(request.GET.get('proveedor'))

    tipo_obj = TiposProductos.objects.filter(pk=tipo).first() if tipo else None
    proveedor_obj = Proveedores.objects.filter(pk=proveedor).first() if proveedor else None

    filtros = {
        'desde': desde,
        'hasta': hasta,
        'tipo': tipo_obj.pk if tipo_obj else None,
        'proveedor': proveedor_obj.pk if proveedor_obj else None,
    }

    texto = (
        f'Desde {desde:%d/%m/%Y} hasta {hasta:%d/%m/%Y} · '
        f'Tipo de producto: {tipo_obj.Nombre_tipo_producto if tipo_obj else "Todos"} · '
        f'Proveedor: {proveedor_obj.nombre_proveedor if proveedor_obj else "Todos"}'
    )

    return filtros, texto, errores


def reportes_consolidados(request, clave=None):
    usuario = usuario_con_acceso(request, 'consolidados')

    if not usuario:
        messages.error(request, 'No tenés permiso para consultar los reportes consolidados.')
        return redirect('panel_principal')

    visibles = _reportes_visibles(usuario)

    if clave is None:
        clave = visibles[0][0]

    if clave not in REPORTES:
        raise Http404('Reporte inexistente.')

    reporte = REPORTES[clave]

    # Reporte sensible: solo con el permiso "Ver reportes sensibles".
    if reporte['sensible'] and not puede_accion(usuario, 'reportes_sensibles'):
        messages.error(
            request,
            f'El reporte "{reporte["titulo"]}" es sensible: '
            'tu perfil no tiene permiso para verlo.'
        )
        return redirect('reportes_consolidados')

    filtros, texto_filtros, errores = _leer_filtros(request)
    for error in errores:
        messages.error(request, error)

    filas, totales = reporte['funcion'](filtros)
    columnas = reporte['columnas']

    # ---------- Exportación a PDF ----------
    if request.GET.get('formato') == 'pdf':
        ahora = timezone.localtime()
        usuario_texto = (
            f'{usuario.Apellido_usuario}, {usuario.Nombre_usuario} '
            f'({usuario.Usuario}) - {usuario.ID_Perfil.Nombre_perfil}'
        )

        pdf = generar_pdf_consolidado(
            reporte, filas, totales, texto_filtros, usuario_texto,
            ahora.strftime('%d/%m/%Y %H:%M'),
            finders.find('inventario/images/logo_agroquimica.png'),
        )

        archivo = f'reporte_{clave}_{ahora:%Y%m%d_%H%M}.pdf'

        LogAuditoria.objects.create(
            ID_Usuario=usuario,
            Seccion='Reportes',
            ID_Registro=0,
            Accion='DESCARGA_PDF',
            Valores_anteriores={},
            Valores_actuales={
                'Documento': f'Reporte consolidado: {reporte["titulo"]}',
                'Archivo': archivo,
                'Filtros': texto_filtros,
                'Filas': len(filas),
            },
        )

        respuesta = HttpResponse(pdf, content_type='application/pdf')
        respuesta['Content-Disposition'] = f'attachment; filename="{archivo}"'
        return respuesta

    # ---------- Grilla paginada ----------
    pagina = paginar(request, filas_formateadas(filas, columnas))

    return render(request, 'inventario/reportes_consolidados.html', {
        'usuario': usuario,
        'activo': 'consolidados',
        'clave': clave,
        'reporte': reporte,
        'visibles': visibles,
        'columnas': columnas,
        'filas': pagina,
        'pagina': pagina,
        'totales': fila_totales(totales, columnas),
        'cantidad': len(filas),
        'filtros': filtros,
        'texto_filtros': texto_filtros,
        'tipos': TiposProductos.objects.order_by('Nombre_tipo_producto'),
        'proveedores': Proveedores.objects.order_by('nombre_proveedor'),
        'query_pdf': _query_pdf(request),
    })


def _query_pdf(request):
    """Los mismos filtros de la pantalla, más formato=pdf (sin la página)."""
    datos = request.GET.copy()
    for clave in ('page', 'por_pagina', 'formato'):
        datos.pop(clave, None)
    datos['formato'] = 'pdf'
    return datos.urlencode()


# ============================================================
# M3 · BANDEJA DE NOTIFICACIONES
# ============================================================

def datos_notificaciones(request):
    """JSON de la bandeja del header."""
    usuario = _usuario()(request)

    if not usuario:
        return JsonResponse({'error': 'Sesión vencida.'}, status=401)

    return JsonResponse(datos_bandeja(usuario))


@require_POST
def leer_notificacion(request, id_notificacion):
    usuario = _usuario()(request)
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not usuario:
        if es_ajax:
            return JsonResponse({'ok': False, 'error': 'Sesión vencida.'}, status=401)
        return redirect('login')

    # Solo las notificaciones dirigidas a su propio perfil.
    notificacion = get_object_or_404(
        notificaciones_de(usuario), ID_Notificacion=id_notificacion
    )
    marcar_leida(usuario, notificacion)

    if es_ajax:
        return JsonResponse({'ok': True, 'no_leidas': no_leidas(usuario)})

    return redirect(request.META.get('HTTP_REFERER') or 'bandeja_notificaciones')


@require_POST
def leer_todas_notificaciones(request):
    usuario = _usuario()(request)
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not usuario:
        if es_ajax:
            return JsonResponse({'ok': False, 'error': 'Sesión vencida.'}, status=401)
        return redirect('login')

    cantidad = marcar_todas_leidas(usuario)

    if es_ajax:
        return JsonResponse({'ok': True, 'marcadas': cantidad, 'no_leidas': 0})

    messages.success(request, f'Se marcaron {cantidad} notificación(es) como leídas.')
    return redirect('bandeja_notificaciones')


def bandeja_notificaciones(request):
    usuario = _usuario()(request)

    if not usuario:
        return redirect('login')

    estado = request.GET.get('estado', '').strip()
    tipo = request.GET.get('tipo', '').strip()

    consulta = notificaciones_de(usuario).select_related('ID_Usuario_lectura')

    if estado == 'no_leidas':
        consulta = consulta.filter(Leida=False)
    elif estado == 'leidas':
        consulta = consulta.filter(Leida=True)

    if tipo:
        consulta = consulta.filter(Tipo=tipo)

    pagina = paginar(request, consulta.order_by('Leida', '-Fecha'))

    tipos = notificaciones_de(usuario).order_by('Tipo').values_list(
        'Tipo', flat=True
    ).distinct()

    return render(request, 'inventario/notificaciones.html', {
        'usuario': usuario,
        'activo': 'notificaciones',
        'notificaciones': pagina,
        'pagina': pagina,
        'estado': estado,
        'tipo': tipo,
        'tipos': tipos,
        'no_leidas': no_leidas(usuario),
    })


# ============================================================
# M3 · CONFIGURACIÓN DE LAS REGLAS
# ============================================================

def configuracion_alertas(request):
    usuario = usuario_con_acceso(request, 'configuracion', gestionar=True)

    if not usuario:
        messages.error(request, 'No tenés permiso para modificar la configuración de alertas.')
        return redirect('panel_principal')

    asegurar_configuracion()
    registros = {c.Clave: c for c in Configuracion.objects.filter(Clave__in=PARAMETROS)}
    errores = {}

    if request.method == 'POST' and request.POST.get('accion') == 'revisar':
        # Evalúa ahora las reglas que corre el job diario.
        antes = Notificacion.objects.count()
        with transaction.atomic():
            lotes = revisar_vencimientos()
            for stock in Stock.objects.select_related('ID_Producto').filter(
                ID_Producto__Estado_producto='Activo'
            ):
                revisar_stock(stock)
        nuevas = Notificacion.objects.count() - antes
        messages.success(
            request,
            f'Reglas evaluadas: {len(lotes)} lote(s) por vencer o vencidos; '
            f'{nuevas} notificación(es) nueva(s).'
        )
        return redirect('configuracion_alertas')

    if request.method == 'POST':
        nuevos = {}

        for clave, (_d, minimo, maximo, titulo, _desc) in PARAMETROS.items():
            texto = request.POST.get(clave, '').strip()
            try:
                valor = int(texto)
            except ValueError:
                errores[clave] = f'"{titulo}" debe ser un número entero.'
                continue
            if not minimo <= valor <= maximo:
                errores[clave] = f'"{titulo}" debe estar entre {minimo} y {maximo}.'
                continue
            nuevos[clave] = str(valor)

        if errores:
            for error in errores.values():
                messages.error(request, error)
        else:
            cambios = 0
            with transaction.atomic():
                for clave, valor in nuevos.items():
                    registro = registros[clave]
                    if registro.Valor == valor:
                        continue
                    antes = snapshot(registro)
                    registro.Valor = valor
                    registro.save(update_fields=['Valor', 'Fecha_modificacion'])
                    registrar_auditoria(
                        usuario, 'Configuracion', registro, 'MODIFICACION',
                        antes, snapshot(registro),
                    )
                    cambios += 1

            if cambios:
                messages.success(request, f'Configuración guardada ({cambios} cambio(s)).')
            else:
                messages.info(request, 'No hubo cambios en la configuración.')
            return redirect('configuracion_alertas')

    parametros = [
        {
            'clave': clave,
            'titulo': titulo,
            'descripcion': descripcion,
            'minimo': minimo,
            'maximo': maximo,
            'defecto': defecto,
            'valor': request.POST.get(clave) if errores else registros[clave].Valor,
            'modificado': registros[clave].Fecha_modificacion,
            'error': errores.get(clave),
        }
        for clave, (defecto, minimo, maximo, titulo, descripcion) in PARAMETROS.items()
    ]

    return render(request, 'inventario/configuracion_alertas.html', {
        'usuario': usuario,
        'activo': 'configuracion',
        'parametros': parametros,
    })
