from datetime import date, datetime, time, timedelta

from django.utils import timezone

from .models import (
    Lotes, MovimientosStock, Productos, Proveedores, Stock, TiposProductos,
)

TIPO_ENTRADA = 'Entrada de lote'

VERDE = '#2e7d32'
ROJO = '#c62828'
NARANJA = '#ef6c00'
AMARILLO = '#f9a825'

MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
         'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

AZUL = '#1565c0'

# Los plazos se nombran con palabras (son categorías, no intervalos
# numéricos). Cada etiqueta es una lista de renglones para el eje X.
ETIQUETAS_TRAMOS = [
    ['Ya vencidos'],
    ['Vencen en menos', 'de 1 mes'],
    ['Vencen en', '1 a 2 meses'],
    ['Vencen en', '2 a 3 meses'],
    ['Vencen en más', 'de 3 meses'],
]
COLORES_TRAMOS = [ROJO, NARANJA, AMARILLO, VERDE, AZUL]

# Filtro de fechas del gráfico 3:
# hasta este largo se agrupa por día; más largo, por mes.
MAX_DIAS_AGRUPADO_POR_DIA = 62
MAX_MESES_RANGO = 60


# ============================================================
# UTILIDADES
# ============================================================

def _periodos(hoy, cantidad=12):
    """Primer día de cada uno de los últimos `cantidad` meses."""
    periodos = []

    for i in range(cantidad - 1, -1, -1):
        m = hoy.month - 1 - i
        periodos.append(date(hoy.year + m // 12, m % 12 + 1, 1))

    return periodos


def _proveedores_por_producto():
    """ID de producto -> lista de IDs de sus proveedores."""
    mapa = {}

    filas = Productos.objects.filter(
        proveedores__isnull=False
    ).values_list('ID_Producto', 'proveedores')

    for pid, prov_id in filas:
        mapa.setdefault(pid, []).append(prov_id)

    return mapa


def filtrar_por_producto(queryset, prefijo, tipo_id=None,
                         subtipo_id=None, proveedor_id=None):
    """Filtra un queryset por tipo, subtipo y proveedor del producto.

    `prefijo` es el camino hasta el producto, por ejemplo 'ID_Lote__ID_Producto__'.
    """
    if tipo_id:
        queryset = queryset.filter(**{prefijo + 'ID_Tipo_producto': tipo_id})
    if subtipo_id:
        queryset = queryset.filter(**{prefijo + 'ID_Subtipo': subtipo_id})
    if proveedor_id:
        queryset = queryset.filter(**{prefijo + 'proveedores': proveedor_id})
    return queryset


# ============================================================
# TIPOS, SUBTIPOS Y PROVEEDORES (para los filtros de los gráficos)
# ============================================================

def _datos_proveedores():
    return [
        {'id': pid, 'nombre': nombre}
        for pid, nombre in Proveedores.objects.order_by(
            'nombre_proveedor'
        ).values_list('ID_Proveedor', 'nombre_proveedor')
    ]


def _datos_tipos():
    tipos = TiposProductos.objects.order_by(
        'Nombre_tipo_producto'
    ).prefetch_related('subtipos')

    return [
        {
            'id': t.ID_Tipo_producto,
            'nombre': t.Nombre_tipo_producto,
            # Los tipos sin subtipos quedan con la lista vacía.
            'subtipos': [
                {'id': s.ID_Subtipo, 'nombre': s.Nombre_subtipo}
                for s in sorted(
                    t.subtipos.all(),
                    key=lambda s: s.Nombre_subtipo.lower()
                )
            ],
        }
        for t in tipos
    ]


# ============================================================
# 1. STOCK ACTUAL VS MÍNIMO
# ============================================================

def _datos_stock(proveedores):
    filas = Stock.objects.filter(
        ID_Producto__Estado_producto='Activo'
    ).values_list(
        'ID_Producto__Nombre_producto',
        'Cantidad_stock',
        'Stock_minimo',
        'ID_Producto__ID_Tipo_producto',
        'ID_Producto__ID_Subtipo',
        'ID_Producto',
    )

    datos = [
        {
            'nombre': producto,
            'stock': stock,
            'minimo': minimo,
            'tipo_id': tipo_id,
            'subtipo_id': subtipo_id,
            'proveedores': proveedores.get(pid, []),
        }
        for producto, stock, minimo, tipo_id, subtipo_id, pid in filas
    ]

    # Los más críticos primero (los que están más por debajo del mínimo).
    datos.sort(key=lambda d: d['stock'] - d['minimo'])

    return datos


# ============================================================
# 2. UNIDADES POR VENCER SEGÚN EL PLAZO
# ============================================================

def _tramo(dias):
    """Índice del tramo según los días que faltan para el vencimiento."""
    if dias < 0:
        return 0
    if dias <= 30:
        return 1
    if dias <= 60:
        return 2
    if dias <= 90:
        return 3
    return 4


def _datos_tramos(hoy, proveedores):
    """Unidades por tramo de vencimiento, separadas por producto.

    La suma se hace en el navegador, así se puede filtrar por
    tipo, subtipo y proveedor.
    """
    filas = Lotes.objects.filter(
        Cantidad_actual__gt=0,
        Fecha_vencimiento__isnull=False,
    ).values_list(
        'ID_Producto',
        'ID_Producto__ID_Tipo_producto',
        'ID_Producto__ID_Subtipo',
        'Fecha_vencimiento',
        'Cantidad_actual',
    )

    productos = {}

    for pid, tipo_id, subtipo_id, vencimiento, cantidad in filas:
        if pid not in productos:
            productos[pid] = {
                'tipo_id': tipo_id,
                'subtipo_id': subtipo_id,
                'proveedores': proveedores.get(pid, []),
                'valores': [0] * len(ETIQUETAS_TRAMOS),
            }

        productos[pid]['valores'][_tramo((vencimiento - hoy).days)] += cantidad

    return {
        'etiquetas': ETIQUETAS_TRAMOS,
        'colores': COLORES_TRAMOS,
        'productos': list(productos.values()),
    }


# ============================================================
# 3. VENTAS VS INGRESOS POR MES
# ============================================================

def datos_evolucion_12_meses(tipo_venta, **filtros):
    """Ventas e ingresos de los últimos 12 meses (con filtros opcionales)."""
    return _datos_evolucion(_periodos(timezone.localdate()), tipo_venta, **filtros)


def _datos_evolucion(periodos, tipo_venta, **filtros):
    claves = [p.strftime('%Y-%m') for p in periodos]
    etiquetas = [f'{MESES[p.month - 1]} {str(p.year)[2:]}' for p in periodos]

    desde = timezone.make_aware(datetime.combine(periodos[0], time.min))

    filas = MovimientosStock.objects.filter(
        Fecha_hora_movimiento__gte=desde,
        Anulado=False,
        ID_Tipo_movimiento__Nombre_tipo_movimiento__in=[
            tipo_venta, TIPO_ENTRADA
        ]
    )

    filas = filtrar_por_producto(
        filas, 'ID_Lote__ID_Producto__', **filtros
    ).values_list(
        'Fecha_hora_movimiento',
        'ID_Tipo_movimiento__Nombre_tipo_movimiento',
        'Cantidad_movimiento_stock',
    )

    ventas = {c: 0 for c in claves}
    ingresos = {c: 0 for c in claves}

    for fecha, tipo, cantidad in filas:
        # Se agrupa por mes en hora local.
        if timezone.is_aware(fecha):
            fecha = timezone.localtime(fecha)

        clave = fecha.strftime('%Y-%m')

        if clave not in ventas:
            continue

        if tipo == tipo_venta:
            ventas[clave] += cantidad
        else:
            ingresos[clave] += cantidad

    return {
        'meses': etiquetas,
        'ventas': [ventas[c] for c in claves],
        'ingresos': [ingresos[c] for c in claves],
        'agrupacion': 'mes',
    }


def datos_evolucion_rango(desde, hasta, tipo_venta, **filtros):
    """Ventas e ingresos entre dos fechas (inclusive).

    Hasta 62 días agrupa por día; más que eso, por mes.
    Lanza ValueError si el rango no es válido.
    """

    if desde > hasta:
        raise ValueError('La fecha "Desde" no puede ser posterior a "Hasta".')

    dias = (hasta - desde).days + 1
    por_dia = dias <= MAX_DIAS_AGRUPADO_POR_DIA

    if por_dia:
        periodos = [desde + timedelta(days=i) for i in range(dias)]

        def clave(f):
            return f.strftime('%Y-%m-%d')

        def etiqueta(p):
            return p.strftime('%d/%m')
    else:
        periodos = []
        actual = desde.replace(day=1)

        while actual <= hasta:
            periodos.append(actual)
            actual = date(
                actual.year + actual.month // 12,
                actual.month % 12 + 1,
                1
            )

        if len(periodos) > MAX_MESES_RANGO:
            raise ValueError('El rango es demasiado largo (máximo 5 años).')

        def clave(f):
            return f.strftime('%Y-%m')

        def etiqueta(p):
            return f'{MESES[p.month - 1]} {str(p.year)[2:]}'

    claves = [clave(p) for p in periodos]

    inicio = timezone.make_aware(datetime.combine(desde, time.min))
    fin = timezone.make_aware(
        datetime.combine(hasta + timedelta(days=1), time.min)
    )

    filas = MovimientosStock.objects.filter(
        Fecha_hora_movimiento__gte=inicio,
        Fecha_hora_movimiento__lt=fin,
        Anulado=False,
        ID_Tipo_movimiento__Nombre_tipo_movimiento__in=[
            tipo_venta, TIPO_ENTRADA
        ]
    )

    filas = filtrar_por_producto(
        filas, 'ID_Lote__ID_Producto__', **filtros
    ).values_list(
        'Fecha_hora_movimiento',
        'ID_Tipo_movimiento__Nombre_tipo_movimiento',
        'Cantidad_movimiento_stock',
    )

    ventas = {c: 0 for c in claves}
    ingresos = {c: 0 for c in claves}

    for fecha, tipo, cantidad in filas:
        if timezone.is_aware(fecha):
            fecha = timezone.localtime(fecha)

        k = clave(fecha)

        if k not in ventas:
            continue

        if tipo == tipo_venta:
            ventas[k] += cantidad
        else:
            ingresos[k] += cantidad

    return {
        'meses': [etiqueta(p) for p in periodos],
        'ventas': [ventas[c] for c in claves],
        'ingresos': [ingresos[c] for c in claves],
        'agrupacion': 'día' if por_dia else 'mes',
    }


# ============================================================
# 4. PRODUCTOS CON MÁS UNIDADES VENCIDAS
# ============================================================

def _datos_vencidos(hoy, proveedores):
    """Unidades vencidas por producto (todos, de mayor a menor).

    El top 10 se arma en el navegador, así se puede recalcular
    al filtrar por tipo, subtipo y proveedor.
    """

    filas = Lotes.objects.filter(
        Cantidad_actual__gt=0,
        Fecha_vencimiento__isnull=False,
        Fecha_vencimiento__lt=hoy,
    ).values_list(
        'ID_Producto',
        'ID_Producto__Nombre_producto',
        'ID_Producto__ID_Tipo_producto',
        'ID_Producto__ID_Subtipo',
        'Cantidad_actual',
    )

    totales = {}

    for pid, producto, tipo_id, subtipo_id, cantidad in filas:
        if pid not in totales:
            totales[pid] = {
                'nombre': producto,
                'tipo_id': tipo_id,
                'subtipo_id': subtipo_id,
                'proveedores': proveedores.get(pid, []),
                'unidades': 0,
            }

        totales[pid]['unidades'] += cantidad

    return sorted(
        totales.values(),
        key=lambda d: d['unidades'],
        reverse=True
    )


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

def generar_reportes(tipo_venta):
    """Devuelve los datos de los 4 gráficos (se dibujan en el navegador)."""

    hoy = timezone.localdate()
    periodos = _periodos(hoy)
    proveedores = _proveedores_por_producto()

    return {
        'tipos': _datos_tipos(),
        'proveedores': _datos_proveedores(),
        'stock': _datos_stock(proveedores),
        'tramos': _datos_tramos(hoy, proveedores),
        'evolucion': _datos_evolucion(periodos, tipo_venta),
        'vencidos': _datos_vencidos(hoy, proveedores),
    }