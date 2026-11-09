"""
MÓDULO DE ANALÍTICA Y VISUALIZACIÓN · Agroquímica del Valle  (Parcial 2 - M1)

Lee la MISMA base de datos MySQL del sistema (conector nativo `MySQLdb`,
del paquete mysqlclient, con las credenciales del archivo .env del
proyecto), transforma los datos con pandas, calcula indicadores con numpy
y genera visualizaciones ejecutivas con matplotlib, exportadas como PNG.

Preguntas de negocio que responde (un gráfico de tipo distinto cada una):

  1. Comparativo categórico  (barras agrupadas)
     ¿Cómo se comportaron las compras, las ventas y las bajas por
     vencimiento en cada período?
  2. Participación  (donut)
     ¿Qué productos concentran la mayor parte de la facturación?
  3. Evolución temporal  (líneas con tendencia)
     ¿Las ventas van en aumento o en baja? Serie de unidades vendidas con
     media móvil, recta de tendencia (numpy.polyfit) y sombreado sobre /
     debajo del promedio (fill_between).
  4. Densidad / concentración  (heatmap)
     ¿En qué días y horas se concentra la operación del depósito?
  5. Dashboard ejecutivo (opcional)  (GridSpec)
     KPIs + los gráficos principales en una sola vista.

Los criterios son los mismos que los de los reportes consolidados (M2):
  - Compras: lotes ingresados (tabla LOTES) de remitos confirmados.
  - Ventas y bajas: movimientos de stock no anulados.
  - Proveedor: el del remito con el que ingresó cada lote.

Uso (desde la carpeta del proyecto, con la base levantada):

    python analitica/analitica.py
    python analitica/analitica.py --desde 2026-01-01 --hasta 2026-12-31
    python analitica/analitica.py --agrupar semana --tipo Fitosanitarios
    python analitica/analitica.py --proveedor Nico --salida analitica/salida

Parámetros:
    --desde / --hasta   Rango de fechas (por defecto: últimos 12 meses).
    --agrupar           dia | semana | mes  (período de los gráficos 1 y 3).
    --tipo              Filtra por tipo de producto (nombre exacto).
    --proveedor         Filtra por proveedor del remito (nombre exacto).
    --top               Cantidad de productos del donut (el resto: "Otros").
    --salida            Carpeta donde se guardan los PNG.

Es reproducible: con la misma base y los mismos parámetros genera las
mismas imágenes (no usa datos aleatorios).
"""

import argparse
import os
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use('Agg')            # sin ventana: solo genera los archivos

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec

import MySQLdb
from dotenv import load_dotenv

# pandas avisa que prefiere SQLAlchemy; con el conector nativo funciona igual.
warnings.filterwarnings('ignore', message='.*pandas only supports SQLAlchemy.*')

RAIZ = Path(__file__).resolve().parent.parent
ZONA = 'America/Argentina/Buenos_Aires'   # la misma de settings.TIME_ZONE

TIPOS_VENTA = ('Egreso por venta', 'Salida por venta')
TIPO_BAJA = 'Salida por vencimiento de producto'
CATEGORIAS = ['Compras', 'Ventas', 'Bajas por vencimiento']

# Paleta de la agroquímica
VERDE, VERDE_OSC, VERDE_CLARO = '#3FA859', '#2C7A3F', '#A7E3A0'
NARANJA, ROJO, GRIS = '#E89B1A', '#C62828', '#B0B0B0'
COLORES = [VERDE_OSC, VERDE, NARANJA, '#6d9eeb', '#A7E3A0', '#8E7CC3', GRIS]

FRECUENCIAS = {'dia': 'D', 'semana': 'W-MON', 'mes': 'MS'}
DIAS_ES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
MESES_ES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
            'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


# ============================================================
# PARÁMETROS
# ============================================================

def leer_parametros():
    hoy = date.today()
    p = argparse.ArgumentParser(description='Analítica de Agroquímica del Valle')
    p.add_argument('--desde', type=date.fromisoformat, default=hoy - timedelta(days=365))
    p.add_argument('--hasta', type=date.fromisoformat, default=hoy)
    p.add_argument('--agrupar', choices=FRECUENCIAS, default='mes')
    p.add_argument('--tipo', default=None, help='Tipo de producto (nombre)')
    p.add_argument('--proveedor', default=None, help='Proveedor del remito (nombre)')
    p.add_argument('--top', type=int, default=5)
    p.add_argument('--salida', type=Path, default=RAIZ / 'analitica' / 'salida')
    args = p.parse_args()

    if args.desde > args.hasta:
        p.error('--desde no puede ser posterior a --hasta')
    if args.top < 1:
        p.error('--top debe ser 1 o más')
    return args


# ============================================================
# CONEXIÓN Y LECTURA (conector nativo MySQLdb)
# ============================================================

def conectar():
    """Conexión con los mismos datos que usa Django (archivo .env)."""
    load_dotenv(RAIZ / '.env')
    return MySQLdb.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        port=int(os.getenv('DB_PORT') or 3306),
        user=os.getenv('DB_USER'),
        passwd=os.getenv('DB_PASSWORD'),
        db=os.getenv('DB_NAME'),
        charset='utf8mb4',
    )


# Movimientos de stock no anulados del período (ventas, bajas y otros).
# Los %s son las fechas desde/hasta, que se pasan aparte con params.

SQL_MOVIMIENTOS = """
    SELECT  m.ID_Movimiento_stock          AS id,
            m.Fecha_hora_movimiento        AS fecha_hora,
            m.Cantidad_movimiento_stock    AS cantidad,
            tm.Nombre_tipo_movimiento      AS tipo_movimiento,
            p.ID_Producto                  AS producto_id,
            p.Nombre_producto              AS producto,
            p.Precio                       AS precio,
            tp.Nombre_tipo_producto        AS tipo_producto,
            pr.nombre_proveedor            AS proveedor
    FROM    MOVIMIENTOS_STOCK m
    JOIN    TIPOS_MOVIMIENTOS tm ON tm.ID_Tipo_movimiento = m.ID_Tipo_movimiento
    JOIN    LOTES l              ON l.ID_Lote = m.ID_Lote
    JOIN    REMITOS r            ON r.ID_Remito = l.ID_Remito
    JOIN    PROVEEDORES pr       ON pr.ID_Proveedor = r.ID_Proveedor
    JOIN    PRODUCTOS p          ON p.ID_Producto = l.ID_Producto
    JOIN    TIPOS_PRODUCTOS tp   ON tp.ID_Tipo_producto = p.ID_Tipo_producto
    WHERE   m.Anulado = 0
      AND   m.Fecha_hora_movimiento >= %s
      AND   m.Fecha_hora_movimiento <  %s
"""

# Compras: lotes ingresados en el período por remitos confirmados
# (mismo criterio que el reporte "Compras vs. ventas" de M2).
SQL_COMPRAS = """
    SELECT  l.ID_Lote                 AS id,
            l.Fecha_ingreso           AS fecha,
            l.Cantidad_ingresada      AS cantidad,
            p.ID_Producto             AS producto_id,
            tp.Nombre_tipo_producto   AS tipo_producto,
            pr.nombre_proveedor       AS proveedor
    FROM    LOTES l
    JOIN    REMITOS r            ON r.ID_Remito = l.ID_Remito
    JOIN    PROVEEDORES pr       ON pr.ID_Proveedor = r.ID_Proveedor
    JOIN    PRODUCTOS p          ON p.ID_Producto = l.ID_Producto
    JOIN    TIPOS_PRODUCTOS tp   ON tp.ID_Tipo_producto = p.ID_Tipo_producto
    WHERE   r.Estado_remito = 'Confirmado'
      AND   l.Fecha_ingreso >= %s
      AND   l.Fecha_ingreso <= %s
"""

# Qué productos entró cada proveedor (para filtrar el stock por proveedor).
SQL_PRODUCTOS_PROVEEDOR = """
    SELECT  DISTINCT l.ID_Producto AS producto_id, pr.nombre_proveedor AS proveedor
    FROM    LOTES l
    JOIN    REMITOS r       ON r.ID_Remito = l.ID_Remito
    JOIN    PROVEEDORES pr  ON pr.ID_Proveedor = r.ID_Proveedor
    WHERE   r.Estado_remito = 'Confirmado'
"""

SQL_STOCK = """
    SELECT  p.ID_Producto AS producto_id, p.Nombre_producto AS producto,
            p.Precio AS precio, s.Cantidad_stock AS stock, s.Stock_minimo AS minimo,
            tp.Nombre_tipo_producto AS tipo_producto
    FROM    STOCK s
    JOIN    PRODUCTOS p        ON p.ID_Producto = s.ID_Producto
    JOIN    TIPOS_PRODUCTOS tp ON tp.ID_Tipo_producto = p.ID_Tipo_producto
    WHERE   p.Estado_producto = 'Activo'
"""


def leer_datos(conn, args):
    """Lee las tablas transaccionales y aplica los filtros de los parámetros."""
    # Las fechas y horas se guardan en UTC: el rango local se pasa a UTC.
    inicio = pd.Timestamp(args.desde, tz=ZONA).tz_convert('UTC').tz_localize(None)
    fin = pd.Timestamp(args.hasta + timedelta(days=1), tz=ZONA).tz_convert('UTC').tz_localize(None)

    mov = pd.read_sql(SQL_MOVIMIENTOS, conn,
                      params=[inicio.to_pydatetime(), fin.to_pydatetime()])
    compras = pd.read_sql(SQL_COMPRAS, conn, params=[args.desde, args.hasta])
    prov = pd.read_sql(SQL_PRODUCTOS_PROVEEDOR, conn)
    stock = pd.read_sql(SQL_STOCK, conn)

    return preparar(mov, compras, prov, stock, args)


def preparar(mov, compras, prov, stock, args):
    """Tipos de datos, categorías de negocio y filtros (pandas)."""
    # UTC -> hora local de la Argentina
    mov['fecha_hora'] = (pd.to_datetime(mov['fecha_hora'])
                         .dt.tz_localize('UTC').dt.tz_convert(ZONA).dt.tz_localize(None))
    # Fecha_ingreso es un DATE (sin hora): no se convierte de zona.
    compras['fecha'] = pd.to_datetime(compras['fecha'])

    for df in (mov, stock):
        df['precio'] = df['precio'].astype(float)
    for df in (mov, compras, stock):
        if 'cantidad' in df:
            df['cantidad'] = df['cantidad'].astype(float)

    # Categoría de negocio de cada movimiento
    mov['categoria'] = np.select(
        [mov['tipo_movimiento'].isin(TIPOS_VENTA),
         mov['tipo_movimiento'] == TIPO_BAJA],
        ['Ventas', 'Bajas por vencimiento'],
        default='Otros',
    )

    # ---- Filtros ----
    if args.tipo:
        mov = mov[mov['tipo_producto'] == args.tipo]
        compras = compras[compras['tipo_producto'] == args.tipo]
        stock = stock[stock['tipo_producto'] == args.tipo]
    if args.proveedor:
        mov = mov[mov['proveedor'] == args.proveedor]
        compras = compras[compras['proveedor'] == args.proveedor]
        ids = prov.loc[prov['proveedor'] == args.proveedor, 'producto_id'].unique()
        stock = stock[stock['producto_id'].isin(ids)]

    return (mov.reset_index(drop=True), compras.reset_index(drop=True),
            stock.reset_index(drop=True))


# ============================================================
# INDICADORES (numpy)
# ============================================================

def indicadores(mov, compras, stock):
    ventas = mov[mov['categoria'] == 'Ventas']
    cant = ventas['cantidad'].to_numpy(dtype=float)
    facturacion = float(np.sum(cant * ventas['precio'].to_numpy(dtype=float)))
    comprado = float(np.sum(compras['cantidad'].to_numpy(dtype=float)))
    vencido = float(np.sum(mov.loc[mov['categoria'] == 'Bajas por vencimiento', 'cantidad']))

    return {
        'unidades_vendidas': int(np.sum(cant)) if cant.size else 0,
        'facturacion': facturacion,
        'egresos': int(cant.size),
        'media_egreso': float(np.mean(cant)) if cant.size else 0.0,
        'mediana_egreso': float(np.median(cant)) if cant.size else 0.0,
        'desvio_egreso': float(np.std(cant)) if cant.size else 0.0,
        'p90_egreso': float(np.percentile(cant, 90)) if cant.size else 0.0,
        'comprado': comprado,
        'pct_perdida': float(np.round(vencido * 100 / comprado, 1)) if comprado else 0.0,
        'stock_valorizado': float(np.sum(stock['stock'].to_numpy(dtype=float)
                                         * stock['precio'].to_numpy(dtype=float))),
        'en_minimo': int(np.sum(stock['stock'].to_numpy() <= stock['minimo'].to_numpy())),
    }


def pesos(valor):
    return '$ ' + f'{valor:,.0f}'.replace(',', '.')


# ============================================================
# TRANSFORMACIONES (pandas)
# ============================================================

def etiqueta_periodo(ts, agrupar):
    if agrupar == 'mes':
        return f'{MESES_ES[ts.month - 1]} {str(ts.year)[2:]}'
    return ts.strftime('%d/%m')


def serie_por_categoria(mov, compras, args):
    """concat + pivot_table + resample: unidades por período y categoría."""
    freq = FRECUENCIAS[args.agrupar]

    datos = pd.concat([
        mov.loc[mov['categoria'].isin(CATEGORIAS), ['fecha_hora', 'categoria', 'cantidad']],
        compras.assign(fecha_hora=compras['fecha'], categoria='Compras')
               [['fecha_hora', 'categoria', 'cantidad']],
    ], ignore_index=True)

    tabla = datos.pivot_table(index='fecha_hora', columns='categoria',
                              values='cantidad', aggfunc='sum')
    if not tabla.empty:
        # label/closed='left': cada período queda con la fecha en que EMPIEZA
        # (con semanas, el lunes de esa semana). Si no, la última semana
        # quedaría con una fecha posterior a --hasta y se perdería.
        tabla = tabla.resample(freq, label='left', closed='left').sum()

    # Todos los períodos del rango, aunque no tengan movimientos.
    inicio = pd.Timestamp(args.desde)
    if args.agrupar == 'mes':
        inicio = inicio.replace(day=1)
    elif args.agrupar == 'semana':
        inicio = inicio - pd.Timedelta(days=inicio.weekday())
    periodos = pd.date_range(inicio, pd.Timestamp(args.hasta), freq=freq)
    tabla = tabla.reindex(periodos, fill_value=0)

    for c in CATEGORIAS:
        if c not in tabla:
            tabla[c] = 0
    return tabla[CATEGORIAS].fillna(0)


def facturacion_por_producto(mov, top):
    ventas = mov[mov['categoria'] == 'Ventas'].copy()
    ventas['importe'] = ventas['cantidad'] * ventas['precio']
    serie = ventas.groupby('producto')['importe'].sum().sort_values(ascending=False)
    if len(serie) > top:
        serie = pd.concat([serie.iloc[:top], pd.Series({'Otros': serie.iloc[top:].sum()})])
    return serie[serie > 0]


def matriz_dia_hora(mov):
    """Cantidad de movimientos por día de la semana (filas) y hora (columnas)."""
    df = mov.assign(dia=mov['fecha_hora'].dt.day_of_week, hora=mov['fecha_hora'].dt.hour)
    mat = df.pivot_table(index='dia', columns='hora', values='id', aggfunc='count')
    horas = range(7, 22)   # horario de atención ampliado
    if not mat.empty:
        horas = range(min(7, int(mat.columns.min())), max(21, int(mat.columns.max())) + 1)
    return mat.reindex(index=range(7), columns=list(horas)).fillna(0)


# ============================================================
# GRÁFICOS (matplotlib)
# ============================================================

def estilo_ejes(ax, titulo):
    ax.set_title(titulo, color=VERDE_OSC, fontweight='bold', fontsize=12)
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='y', linestyle='--', alpha=0.35)


def sin_datos(ax, texto='Sin datos para los filtros elegidos'):
    ax.text(0.5, 0.5, texto, ha='center', va='center', color='gray',
            transform=ax.transAxes, fontsize=11)
    ax.set_xticks([])
    ax.set_yticks([])


def g1_barras_agrupadas(tabla, args, ax):
    """1. Comparativo categórico: compras, ventas y bajas por período."""
    estilo_ejes(ax, 'Compras, ventas y bajas por vencimiento (unidades)')
    if tabla.to_numpy().sum() == 0:
        return sin_datos(ax)

    x = np.arange(len(tabla))
    ancho = 0.27
    for i, (col, color) in enumerate(zip(tabla.columns, [VERDE_OSC, VERDE, NARANJA])):
        barras = ax.bar(x + (i - 1) * ancho, tabla[col], ancho, label=col, color=color)
        ax.bar_label(barras, labels=[f'{v:.0f}' if v else '' for v in tabla[col]],
                     fontsize=7, padding=2)
    ax.set_xticks(x, [etiqueta_periodo(t, args.agrupar) for t in tabla.index],
                  rotation=45 if len(x) > 12 else 0, fontsize=8)
    ax.set_ylabel('Unidades')
    ax.legend(frameon=False)


def g2_donut(serie, ax):
    """2. Participación: qué productos concentran la facturación."""
    ax.set_title('Participación en la facturación', color=VERDE_OSC,
                 fontweight='bold', fontsize=12)
    if serie.empty:
        return sin_datos(ax)

    # Con muchos productos: colores distintos para cada uno (escala de 20).
    if len(serie) <= len(COLORES):
        colores = COLORES[:len(serie)]
    else:
        colores = plt.cm.tab20(np.arange(len(serie)) % 20)

    # Si hay porciones chicas (< 3 %), sus textos se superpondrían: los
    # nombres pasan a una leyenda al costado y el % se muestra solo en
    # las porciones grandes.
    porcentajes = serie.to_numpy() * 100 / serie.sum()
    MINIMO = 3
    con_leyenda = bool((porcentajes < MINIMO).any())
    etiquetas = None if con_leyenda else list(serie.index)

    porciones, textos, pct = ax.pie(
        serie.to_numpy(), labels=etiquetas, colors=colores,
        autopct=lambda p: f'{p:.1f}%' if p >= MINIMO else '',
        startangle=90, pctdistance=0.78,
        wedgeprops={'width': 0.42, 'edgecolor': 'white'},
    )

    if con_leyenda:
        ax.legend(
            porciones,
            [f'{n} ({p:.1f}%)'.replace('.', ',') for n, p in zip(serie.index, porcentajes)],
            loc='center left', bbox_to_anchor=(1.02, 0.5),
            fontsize=7, frameon=False,
        )

    for t in pct:
        t.set_color('white')
        t.set_fontweight('bold')
        t.set_fontsize(8)
    ax.text(0, 0, pesos(serie.sum()), ha='center', va='center',
            fontweight='bold', color=VERDE_OSC, fontsize=11)
    ax.axis('equal')


def g3_tendencia(tabla, args, ax):
    """3. Evolución temporal: ventas con media móvil y tendencia lineal."""
    estilo_ejes(ax, 'Evolución de las unidades vendidas')
    ventas = tabla['Ventas'].astype(float)
    if ventas.sum() == 0:
        return sin_datos(ax)

    x = np.arange(len(ventas))
    y = ventas.to_numpy()
    media = float(np.mean(y))

    ax.plot(x, y, marker='o', color=VERDE_OSC, linewidth=2, label='Unidades vendidas')
    ax.plot(x, ventas.rolling(3, min_periods=1).mean(), color=VERDE, linestyle=':',
            linewidth=2, label='Media móvil (3 períodos)')

    if len(x) >= 2:
        pendiente, ordenada = np.polyfit(x, y, 1)
        ax.plot(x, pendiente * x + ordenada, color=NARANJA, linestyle='--',
                label=f'Tendencia ({pendiente:+.1f} u. por período)')

    ax.axhline(media, color=GRIS, linewidth=1)
    ax.fill_between(x, y, media, where=y >= media, interpolate=True,
                    color=VERDE_CLARO, alpha=0.5, label='Sobre el promedio')
    ax.fill_between(x, y, media, where=y < media, interpolate=True,
                    color='#F4B6B6', alpha=0.5, label='Debajo del promedio')

    ax.set_xticks(x, [etiqueta_periodo(t, args.agrupar) for t in ventas.index],
                  rotation=45 if len(x) > 12 else 0, fontsize=8)
    ax.set_ylabel('Unidades')
    ax.legend(frameon=False, fontsize=8, ncol=2)


def g4_heatmap(mat, ax, fig):
    """4. Densidad: movimientos por día de la semana y hora."""
    ax.set_title('Movimientos registrados por día y hora', color=VERDE_OSC,
                 fontweight='bold', fontsize=12)
    if mat.to_numpy().sum() == 0:
        return sin_datos(ax)

    valores = mat.to_numpy()
    im = ax.imshow(valores, cmap='Greens', aspect='auto')
    fig.colorbar(im, ax=ax, label='N° de movimientos')
    ax.set_yticks(range(7), DIAS_ES)
    ax.set_xticks(range(len(mat.columns)), [f'{h:02d}:00' for h in mat.columns],
                  rotation=45, fontsize=8)

    umbral = valores.max() * 0.6
    for i in range(valores.shape[0]):
        for j in range(valores.shape[1]):
            if valores[i, j]:
                ax.text(j, i, int(valores[i, j]), ha='center', va='center', fontsize=8,
                        color='white' if valores[i, j] > umbral else '#1c2a23')


def guardar(fig, carpeta, nombre):
    ruta = carpeta / nombre
    fig.savefig(ruta, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  ✓ {ruta}')
    return ruta


def subtitulo(args):
    partes = [f'{args.desde:%d/%m/%Y} al {args.hasta:%d/%m/%Y}']
    if args.tipo:
        partes.append(f'Tipo: {args.tipo}')
    if args.proveedor:
        partes.append(f'Proveedor: {args.proveedor}')
    return ' · '.join(partes)


def dashboard(tabla, serie, mat, kpi, args, carpeta):
    """5. Panel integrado (GridSpec): KPIs + gráficos principales."""
    fig = plt.figure(figsize=(16, 10))
    gs = GridSpec(3, 4, figure=fig, height_ratios=[0.55, 2, 2], hspace=0.55, wspace=0.35)
    fig.suptitle(f'Dashboard ejecutivo · Agroquímica del Valle\n{subtitulo(args)}',
                 color=VERDE_OSC, fontweight='bold', fontsize=15)

    tarjetas = [
        ('Unidades vendidas', f'{kpi["unidades_vendidas"]:,}'.replace(',', '.')),
        ('Facturación estimada', pesos(kpi['facturacion'])),
        ('Pérdida por vencimiento (% de lo comprado)', f'{kpi["pct_perdida"]:.1f} %'.replace('.', ',')),
        ('Stock valorizado', pesos(kpi['stock_valorizado'])),
    ]
    for i, (titulo, valor) in enumerate(tarjetas):
        ax = fig.add_subplot(gs[0, i])
        ax.axis('off')
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                                   color='#eaf4e6', zorder=0))
        ax.text(0.5, 0.68, titulo, ha='center', color='#4a5a52', fontsize=10,
                transform=ax.transAxes)
        ax.text(0.5, 0.25, valor, ha='center', color=VERDE_OSC, fontsize=15,
                fontweight='bold', transform=ax.transAxes)

    g1_barras_agrupadas(tabla, args, fig.add_subplot(gs[1, :3]))
    g2_donut(serie, fig.add_subplot(gs[1, 3]))
    g3_tendencia(tabla, args, fig.add_subplot(gs[2, :2]))
    g4_heatmap(mat, fig.add_subplot(gs[2, 2:]), fig)

    return guardar(fig, carpeta, '5_dashboard_ejecutivo.png')


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def generar(mov, compras, stock, args):
    """Indicadores, transformaciones y gráficos a partir de los datos leídos."""
    print(f'Movimientos leídos: {len(mov)} · Lotes comprados: {len(compras)} · '
          f'Productos con stock: {len(stock)}')

    kpi = indicadores(mov, compras, stock)
    print('\nIndicadores (numpy):')
    print(f'  Unidades vendidas ........ {kpi["unidades_vendidas"]}')
    print(f'  Facturación estimada ..... {pesos(kpi["facturacion"])}')
    print(f'  Egresos registrados ...... {kpi["egresos"]}')
    print(f'  Egreso medio / mediana ... {kpi["media_egreso"]:.1f} / {kpi["mediana_egreso"]:.1f} u.')
    print(f'  Desvío estándar egreso ... {kpi["desvio_egreso"]:.1f} u. (P90: {kpi["p90_egreso"]:.1f})')
    print(f'  Unidades compradas ....... {kpi["comprado"]:.0f}')
    print(f'  Pérdida por vencimiento .. {kpi["pct_perdida"]:.1f} % de lo comprado')
    print(f'  Stock valorizado ......... {pesos(kpi["stock_valorizado"])}')
    print(f'  Productos en stock mínimo  {kpi["en_minimo"]}')

    tabla = serie_por_categoria(mov, compras, args)
    serie = facturacion_por_producto(mov, args.top)
    mat = matriz_dia_hora(mov)

    print('\nGráficos generados:')

    fig, ax = plt.subplots(figsize=(12, 5))
    g1_barras_agrupadas(tabla, args, ax)
    fig.suptitle(subtitulo(args), fontsize=9, color='gray', y=0.02)
    guardar(fig, args.salida, '1_compras_ventas_bajas.png')

    fig, ax = plt.subplots(figsize=(7, 7))
    g2_donut(serie, ax)
    fig.suptitle(subtitulo(args), fontsize=9, color='gray', y=0.06)
    guardar(fig, args.salida, '2_participacion_facturacion.png')

    fig, ax = plt.subplots(figsize=(12, 5))
    g3_tendencia(tabla, args, ax)
    fig.suptitle(subtitulo(args), fontsize=9, color='gray', y=0.02)
    guardar(fig, args.salida, '3_evolucion_ventas.png')

    fig, ax = plt.subplots(figsize=(12, 4.5))
    g4_heatmap(mat, ax, fig)
    fig.suptitle(subtitulo(args), fontsize=9, color='gray', y=0.0)
    guardar(fig, args.salida, '4_heatmap_dia_hora.png')

    dashboard(tabla, serie, mat, kpi, args, args.salida)

    # Tabla resumen para el informe
    resumen = tabla.copy()
    resumen.index = [etiqueta_periodo(t, args.agrupar) for t in resumen.index]
    resumen.to_csv(args.salida / 'resumen_por_periodo.csv', encoding='utf-8-sig')
    print(f'  ✓ {args.salida / "resumen_por_periodo.csv"}')


def main():
    # La consola de Windows usa cp1252: se fuerza UTF-8 para los acentos y el ✓.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    args = leer_parametros()
    args.salida.mkdir(parents=True, exist_ok=True)

    print(f'Analítica · {subtitulo(args)} · agrupado por {args.agrupar}')

    try:
        conn = conectar()
    except MySQLdb.Error as e:
        sys.exit(f'No se pudo conectar a la base de datos: {e}')

    try:
        mov, compras, stock = leer_datos(conn, args)
    finally:
        conn.close()

    generar(mov, compras, stock, args)


if __name__ == '__main__':
    main()
    