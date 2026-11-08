"""
Reportes consolidados · Agroquímica del Valle  (Parcial 2 - M2)

Cada reporte cruza datos de dos o más procesos transaccionales:

  1. COMPRAS VS. VENTAS POR PRODUCTO
     Ingreso de lotes por remito (compra) + Egresos por venta + Bajas por
     vencimiento. Unidades compradas, vendidas y perdidas de cada producto
     en el período, con la facturación estimada (vendido × precio).

  2. ROTACIÓN DE COMPRAS POR PROVEEDOR
     Remitos (compra) + Egresos por venta + Bajas por vencimiento. Para
     los lotes que entró cada proveedor en el período: cuánto se vendió,
     cuánto se venció y qué porcentaje rotó.

  3. PÉRDIDAS POR VENCIMIENTO (sensible: montos en pesos)
     Bajas por vencimiento + Remito/proveedor de origen + Egresos del lote.
     Cada baja con lo que se había vendido del lote y la pérdida valorizada.
     Solo lo ven los perfiles con el permiso "Ver reportes sensibles".

Todos tienen filtros de rango de fechas, tipo de producto y proveedor.
El filtro de proveedor es SIEMPRE el proveedor del remito con el que
entró cada lote (no la lista de proveedores posibles del producto), así
los tres reportes dan los mismos números para el mismo filtro.

Las vistas los muestran en una grilla paginada con totales al pie y los
exportan a PDF (pdf_consolidado.py).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from .models import Lotes, MovimientosStock, Productos, Remitos

TIPOS_VENTA = ('Egreso por venta', 'Salida por venta')
TIPO_BAJA = 'Salida por vencimiento de producto'


# ------------------------------------------------------------
# FILTROS
# ------------------------------------------------------------

def _rango_aware(desde, hasta):
    """[desde 00:00, hasta+1 00:00) en la zona horaria del sistema."""
    inicio = timezone.make_aware(datetime.combine(desde, time.min))
    fin = timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min))
    return inicio, fin


def _filtro_lote(prefijo_lote, filtros):
    """Q con los filtros de tipo de producto y proveedor sobre un lote.

    prefijo_lote: camino desde el modelo consultado hasta el lote
      - ''           si se consulta Lotes
      - 'ID_Lote__'  si se consulta MovimientosStock

    Tipo: el del producto del lote.
    Proveedor: el del remito con el que ingresó el lote.
    """
    q = Q()
    if filtros.get('tipo'):
        q &= Q(**{prefijo_lote + 'ID_Producto__ID_Tipo_producto_id': filtros['tipo']})
    if filtros.get('proveedor'):
        q &= Q(**{prefijo_lote + 'ID_Remito__ID_Proveedor_id': filtros['proveedor']})
    return q


def _pct(parte, total):
    return round(parte * 100 / total, 1) if total else 0.0


# ------------------------------------------------------------
# 1. COMPRAS VS. VENTAS POR PRODUCTO
# ------------------------------------------------------------

def compras_ventas(filtros):
    inicio, fin = _rango_aware(filtros['desde'], filtros['hasta'])

    # Compras: lotes que ingresaron en el período (remitos no anulados).
    compras = dict(
        Lotes.objects.filter(
            Fecha_ingreso__gte=filtros['desde'],
            Fecha_ingreso__lte=filtros['hasta'],
        ).exclude(ID_Remito__Estado_remito='Anulado')
        .filter(_filtro_lote('', filtros))
        .values('ID_Producto').annotate(t=Sum('Cantidad_ingresada'))
        .values_list('ID_Producto', 't')
    )

    def movimientos(tipos):
        return dict(
            MovimientosStock.objects.filter(
                Fecha_hora_movimiento__gte=inicio,
                Fecha_hora_movimiento__lt=fin,
                Anulado=False,
                ID_Tipo_movimiento__Nombre_tipo_movimiento__in=tipos,
                ID_Lote__isnull=False,
            ).filter(_filtro_lote('ID_Lote__', filtros))
            .values('ID_Lote__ID_Producto').annotate(t=Sum('Cantidad_movimiento_stock'))
            .values_list('ID_Lote__ID_Producto', 't')
        )

    ventas = movimientos(TIPOS_VENTA)
    bajas = movimientos([TIPO_BAJA])

    ids = set(compras) | set(ventas) | set(bajas)
    productos = Productos.objects.filter(pk__in=ids).select_related(
        'ID_Tipo_producto', 'stock'
    )

    filas = []
    for p in productos:
        comprado = compras.get(p.pk) or 0
        vendido = ventas.get(p.pk) or 0
        vencido = bajas.get(p.pk) or 0
        precio = p.Precio or Decimal('0')
        stock = getattr(getattr(p, 'stock', None), 'Cantidad_stock', 0) or 0

        filas.append({
            'producto': p.Nombre_producto,
            'tipo': p.ID_Tipo_producto.Nombre_tipo_producto if p.ID_Tipo_producto else '—',
            'comprado': comprado,
            'vendido': vendido,
            'vencido': vencido,
            'stock': stock,
            'precio': precio,
            'facturacion': precio * vendido,
            # Puede superar el 100 %: se venden también lotes de períodos anteriores.
            'pct_vendido': _pct(vendido, comprado),
        })

    filas.sort(key=lambda f: (-f['facturacion'], f['producto'].lower()))

    t_comprado = sum(f['comprado'] for f in filas)
    t_vendido = sum(f['vendido'] for f in filas)
    totales = {
        'producto': f'{len(filas)} productos',
        'comprado': t_comprado,
        'vendido': t_vendido,
        'vencido': sum(f['vencido'] for f in filas),
        'stock': sum(f['stock'] for f in filas),
        'facturacion': sum((f['facturacion'] for f in filas), Decimal('0')),
        'pct_vendido': _pct(t_vendido, t_comprado),
    }
    return filas, totales


# ------------------------------------------------------------
# 2. ROTACIÓN DE COMPRAS POR PROVEEDOR
# ------------------------------------------------------------

def rotacion_proveedores(filtros):
    remitos = Remitos.objects.filter(
        Fecha_remito__gte=filtros['desde'],
        Fecha_remito__lte=filtros['hasta'],
        Estado_remito='Confirmado',
    ).select_related('ID_Proveedor')

    if filtros.get('proveedor'):
        remitos = remitos.filter(ID_Proveedor_id=filtros['proveedor'])

    lotes = Lotes.objects.filter(ID_Remito__in=remitos).select_related(
        'ID_Remito__ID_Proveedor'
    )
    if filtros.get('tipo'):
        lotes = lotes.filter(ID_Producto__ID_Tipo_producto_id=filtros['tipo'])

    lotes = list(lotes)
    ids_lotes = [l.pk for l in lotes]

    def por_lote(tipos):
        return dict(
            MovimientosStock.objects.filter(
                ID_Lote_id__in=ids_lotes,
                Anulado=False,
                ID_Tipo_movimiento__Nombre_tipo_movimiento__in=tipos,
            ).values('ID_Lote').annotate(t=Sum('Cantidad_movimiento_stock'))
            .values_list('ID_Lote', 't')
        )

    vendido_lote = por_lote(TIPOS_VENTA)
    vencido_lote = por_lote([TIPO_BAJA])

    datos = {}
    for lote in lotes:
        proveedor = lote.ID_Remito.ID_Proveedor
        d = datos.setdefault(proveedor.pk, {
            'proveedor': proveedor.nombre_proveedor,
            'remitos': set(),
            'lotes': 0,
            'comprado': 0,
            'vendido': 0,
            'vencido': 0,
            'disponible': 0,
        })
        d['remitos'].add(lote.ID_Remito_id)
        d['lotes'] += 1
        d['comprado'] += lote.Cantidad_ingresada or 0
        d['vendido'] += vendido_lote.get(lote.pk) or 0
        d['vencido'] += vencido_lote.get(lote.pk) or 0
        d['disponible'] += lote.Cantidad_actual or 0

    filas = []
    for d in datos.values():
        d['remitos'] = len(d['remitos'])
        d['pct_rotacion'] = _pct(d['vendido'], d['comprado'])
        d['pct_perdida'] = _pct(d['vencido'], d['comprado'])
        filas.append(d)

    filas.sort(key=lambda f: (-f['comprado'], f['proveedor'].lower()))

    t = {k: sum(f[k] for f in filas)
         for k in ('remitos', 'lotes', 'comprado', 'vendido', 'vencido', 'disponible')}
    t['proveedor'] = f'{len(filas)} proveedores'
    t['pct_rotacion'] = _pct(t['vendido'], t['comprado'])
    t['pct_perdida'] = _pct(t['vencido'], t['comprado'])
    return filas, t


# ------------------------------------------------------------
# 3. PÉRDIDAS POR VENCIMIENTO (sensible)
# ------------------------------------------------------------

def perdidas_vencimiento(filtros):
    inicio, fin = _rango_aware(filtros['desde'], filtros['hasta'])

    bajas = MovimientosStock.objects.filter(
        Fecha_hora_movimiento__gte=inicio,
        Fecha_hora_movimiento__lt=fin,
        Anulado=False,
        ID_Tipo_movimiento__Nombre_tipo_movimiento=TIPO_BAJA,
        ID_Lote__isnull=False,
    ).filter(_filtro_lote('ID_Lote__', filtros)).select_related(
        'ID_Lote__ID_Producto__ID_Tipo_producto',
        'ID_Lote__ID_Remito__ID_Proveedor',
    ).order_by('-Fecha_hora_movimiento')

    bajas = list(bajas)

    vendido_lote = dict(
        MovimientosStock.objects.filter(
            ID_Lote_id__in={b.ID_Lote_id for b in bajas},
            Anulado=False,
            ID_Tipo_movimiento__Nombre_tipo_movimiento__in=TIPOS_VENTA,
        ).values('ID_Lote').annotate(t=Sum('Cantidad_movimiento_stock'))
        .values_list('ID_Lote', 't')
    )

    filas = []
    for b in bajas:
        lote = b.ID_Lote
        producto = lote.ID_Producto
        remito = lote.ID_Remito
        precio = producto.Precio or Decimal('0')

        filas.append({
            'fecha': timezone.localtime(b.Fecha_hora_movimiento).date(),
            'producto': producto.Nombre_producto,
            'lote': lote.Numero_lote,
            'proveedor': remito.ID_Proveedor.nombre_proveedor if remito else '—',
            'remito': remito.Numero_remito if remito else '—',
            'comprado': lote.Cantidad_ingresada or 0,
            'vendido': vendido_lote.get(lote.pk) or 0,
            'vencido': b.Cantidad_movimiento_stock,
            'precio': precio,
            'perdida': precio * b.Cantidad_movimiento_stock,
        })

    totales = {
        'producto': f'{len(filas)} bajas',
        'comprado': sum(f['comprado'] for f in filas),
        'vendido': sum(f['vendido'] for f in filas),
        'vencido': sum(f['vencido'] for f in filas),
        'perdida': sum((f['perdida'] for f in filas), Decimal('0')),
    }
    return filas, totales


# ------------------------------------------------------------
# CATÁLOGO DE REPORTES
# Columnas: (clave, título, formato). Formatos: texto, entero, moneda,
# pct, fecha. El pie de la tabla muestra la fila "totales".
# ------------------------------------------------------------

REPORTES = {
    'compras-ventas': {
        'titulo': 'Compras vs. ventas por producto',
        'descripcion': (
            'Unidades compradas (lotes ingresados por remito), vendidas (egresos) '
            'y dadas de baja por vencimiento de cada producto en el período, con la '
            'facturación estimada a precio de lista.'
        ),
        'procesos': 'Remitos / ingreso de lotes · Egresos por venta · Bajas por vencimiento',
        'sensible': False,
        'funcion': compras_ventas,
        'columnas': [
            ('producto', 'Producto', 'texto'),
            ('tipo', 'Tipo', 'texto'),
            ('comprado', 'Comprado', 'entero'),
            ('vendido', 'Vendido', 'entero'),
            ('vencido', 'Vencido', 'entero'),
            ('stock', 'Stock actual', 'entero'),
            ('precio', 'Precio', 'moneda'),
            ('facturacion', 'Facturación', 'moneda'),
            ('pct_vendido', '% vendido', 'pct'),
        ],
    },
    'proveedores': {
        'titulo': 'Rotación de compras por proveedor',
        'descripcion': (
            'Para los remitos confirmados del período, cuántas unidades entró cada '
            'proveedor, cuántas se vendieron, cuántas se vencieron y qué porcentaje rotó.'
        ),
        'procesos': 'Remitos (compras) · Egresos por venta · Bajas por vencimiento',
        'sensible': False,
        'funcion': rotacion_proveedores,
        'columnas': [
            ('proveedor', 'Proveedor', 'texto'),
            ('remitos', 'Remitos', 'entero'),
            ('lotes', 'Lotes', 'entero'),
            ('comprado', 'Comprado', 'entero'),
            ('vendido', 'Vendido', 'entero'),
            ('vencido', 'Vencido', 'entero'),
            ('disponible', 'Disponible', 'entero'),
            ('pct_rotacion', '% rotación', 'pct'),
            ('pct_perdida', '% pérdida', 'pct'),
        ],
    },
    'perdidas': {
        'titulo': 'Pérdidas por vencimiento',
        'descripcion': (
            'Cada baja por vencimiento del período con el proveedor y remito del lote, '
            'lo que se había vendido de ese lote y la pérdida estimada a precio de lista.'
        ),
        'procesos': 'Bajas por vencimiento · Remitos (proveedor) · Egresos por venta',
        'sensible': True,
        'funcion': perdidas_vencimiento,
        'columnas': [
            ('fecha', 'Fecha baja', 'fecha'),
            ('producto', 'Producto', 'texto'),
            ('lote', 'Lote', 'texto'),
            ('proveedor', 'Proveedor', 'texto'),
            ('remito', 'Remito', 'texto'),
            ('comprado', 'Ingresado', 'entero'),
            ('vendido', 'Vendido', 'entero'),
            ('vencido', 'Dado de baja', 'entero'),
            ('precio', 'Precio', 'moneda'),
            ('perdida', 'Pérdida', 'moneda'),
        ],
    },
}


# ------------------------------------------------------------
# FORMATO (pantalla y PDF usan el mismo)
# ------------------------------------------------------------

def _miles(n):
    return f'{n:,}'.replace(',', '.')


def formatear(valor, formato):
    if valor is None or valor == '':
        return '' if formato != 'texto' else '—'
    if formato == 'entero':
        return _miles(int(valor))
    if formato == 'moneda':
        entero, dec = f'{Decimal(valor):,.2f}'.split('.')
        return f'$ {entero.replace(",", ".")},{dec}'
    if formato == 'pct':
        return f'{valor:.1f} %'.replace('.', ',')
    if formato == 'fecha':
        return valor.strftime('%d/%m/%Y')
    return str(valor)


def filas_formateadas(filas, columnas):
    """Lista de listas de (texto, formato) para la grilla y el PDF."""
    return [
        [(formatear(f.get(c), fmt), fmt) for c, _t, fmt in columnas]
        for f in filas
    ]


def fila_totales(totales, columnas):
    """Fila del pie: 'TOTALES' en la primera columna y los totales formateados."""
    fila = []
    for i, (clave, _titulo, formato) in enumerate(columnas):
        valor = totales.get(clave)
        if i == 0:
            texto = 'TOTALES' + (f' · {formatear(valor, formato)}' if valor not in (None, '') else '')
            fila.append((texto, 'texto'))
        elif valor is not None:
            fila.append((formatear(valor, formato), formato))
        else:
            fila.append(('', formato))
    return fila
