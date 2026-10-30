from datetime import date, datetime, time

from django.utils import timezone

from .models import Lotes, MovimientosStock, Stock

TIPO_ENTRADA = 'Entrada de lote'

VERDE = '#2e7d32'
ROJO = '#c62828'
NARANJA = '#ef6c00'
AMARILLO = '#f9a825'

MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
         'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

ETIQUETAS_TRAMOS = ['Vencidos', '0-30 días', '31-60 días', '61-90 días']
COLORES_TRAMOS = [ROJO, NARANJA, AMARILLO, VERDE]


# ============================================================
# UTILIDADES
# ============================================================

def _etiqueta(producto, marca):
    """Devuelve 'producto (marca)' o solo 'producto' si no hay marca."""
    return f'{producto} ({marca})' if marca else producto


def _periodos(hoy, cantidad=12):
    """Primer día de cada uno de los últimos `cantidad` meses."""
    periodos = []

    for i in range(cantidad - 1, -1, -1):
        m = hoy.month - 1 - i
        periodos.append(date(hoy.year + m // 12, m % 12 + 1, 1))

    return periodos


# ============================================================
# 1. STOCK ACTUAL VS MÍNIMO
# ============================================================

def _datos_stock():
    filas = Stock.objects.filter(
        ID_Producto__Estado_producto='Activo'
    ).values_list(
        'ID_Producto__Nombre_producto',
        'ID_Producto__Marca',
        'Cantidad_stock',
        'Stock_minimo',
    )

    datos = [
        {
            'nombre': _etiqueta(producto, marca),
            'stock': stock,
            'minimo': minimo,
        }
        for producto, marca, stock, minimo in filas
    ]

    # Los más críticos primero (los que están más por debajo del mínimo).
    datos.sort(key=lambda d: d['stock'] - d['minimo'])

    return datos


# ============================================================
# 2. UNIDADES POR VENCER SEGÚN EL PLAZO
# ============================================================

def _datos_tramos(hoy):
    valores = [0, 0, 0, 0]

    filas = Lotes.objects.filter(
        Cantidad_actual__gt=0,
        Fecha_vencimiento__isnull=False,
    ).values_list('Fecha_vencimiento', 'Cantidad_actual')

    for vencimiento, cantidad in filas:
        dias = (vencimiento - hoy).days

        if dias < 0:
            valores[0] += cantidad
        elif dias <= 30:
            valores[1] += cantidad
        elif dias <= 60:
            valores[2] += cantidad
        elif dias <= 90:
            valores[3] += cantidad
        # Lo que vence a más de 90 días no se cuenta.

    return {
        'etiquetas': ETIQUETAS_TRAMOS,
        'valores': valores,
        'colores': COLORES_TRAMOS,
    }


# ============================================================
# 3. VENTAS VS INGRESOS POR MES
# ============================================================

def _datos_evolucion(periodos, tipo_venta):
    claves = [p.strftime('%Y-%m') for p in periodos]
    etiquetas = [f'{MESES[p.month - 1]} {str(p.year)[2:]}' for p in periodos]

    desde = timezone.make_aware(datetime.combine(periodos[0], time.min))

    filas = MovimientosStock.objects.filter(
        Fecha_hora_movimiento__gte=desde,
        ID_Tipo_movimiento__Nombre_tipo_movimiento__in=[
            tipo_venta, TIPO_ENTRADA
        ]
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
    }


# ============================================================
# 4. PRODUCTOS CON MÁS UNIDADES VENCIDAS
# ============================================================

def _datos_vencidos(hoy):
    filas = Lotes.objects.filter(
        Cantidad_actual__gt=0,
        Fecha_vencimiento__isnull=False,
        Fecha_vencimiento__lt=hoy,
    ).values_list(
        'ID_Producto__Nombre_producto',
        'ID_Producto__Marca',
        'Cantidad_actual',
    )

    totales = {}

    for producto, marca, cantidad in filas:
        nombre = _etiqueta(producto, marca)
        totales[nombre] = totales.get(nombre, 0) + cantidad

    # Top 10, el mayor primero (queda arriba en el gráfico).
    top = sorted(totales.items(), key=lambda x: x[1], reverse=True)[:10]

    return [{'nombre': n, 'unidades': u} for n, u in top]


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

def generar_reportes(tipo_venta):
    """Devuelve los datos de los 4 gráficos (se dibujan en el navegador)."""

    hoy = timezone.localdate()
    periodos = _periodos(hoy)

    return {
        'stock': _datos_stock(),
        'tramos': _datos_tramos(hoy),
        'evolucion': _datos_evolucion(periodos, tipo_venta),
        'vencidos': _datos_vencidos(hoy),
    }