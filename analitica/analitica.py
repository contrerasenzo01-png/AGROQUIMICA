"""
MÓDULO DE ANALÍTICA Y VISUALIZACIÓN · Agroquímica del Valle  (Parcial 2 - M1)

Lee la MISMA base de datos MySQL del sistema (conector nativo `MySQLdb`,
del paquete mysqlclient, con las credenciales del archivo .env del
proyecto), transforma los datos con pandas, calcula indicadores con numpy
y genera visualizaciones ejecutivas con matplotlib, exportadas como PNG.

Preguntas de negocio que responde (un gráfico de tipo distinto cada una):

  1. Comparativo categórico  (barras agrupadas)
     ¿Cómo se comportaron los ingresos de lotes, los egresos por venta y
     los egresos por vencimiento en cada período?
  2. Participación  (donut)
     ¿Qué productos concentran la mayor parte de la facturación?
  3. Evolución temporal  (líneas con tendencia)
     ¿Los egresos por venta van en aumento o en baja? Serie de unidades con
     media móvil, recta de tendencia (numpy.polyfit) y sombreado sobre /
     debajo del promedio (fill_between).
  4. Densidad / concentración  (heatmap)
     ¿En qué días y horas se concentra la operación del depósito?
  5. Dashboard ejecutivo (opcional)  (GridSpec)
     KPIs + los gráficos principales en una sola vista.

Los criterios son los mismos que los de los reportes consolidados (M2):
  - Ingresos de lotes: lotes ingresados (tabla LOTES) por remitos confirmados.
  - Egresos por venta y por vencimiento: movimientos de stock no anulados.
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

Recorrido del programa (función main, al final del archivo):
    1. leer_parametros()  -> lee los filtros de la línea de comandos.
    2. conectar()         -> abre la conexión a MySQL con los datos del .env.
    3. leer_datos()       -> ejecuta las consultas SQL con pandas (read_sql).
    4. preparar()         -> convierte tipos, clasifica y aplica filtros.
    5. generar()          -> calcula indicadores (numpy), arma las tablas
                             (pandas) y dibuja los gráficos (matplotlib).
"""

# ============================================================
# IMPORTACIONES
# ============================================================

# --- Librería estándar de Python ---
import argparse                       # lee los parámetros de la terminal (--desde, --top, ...)
import os                             # lee variables de entorno (usuario y clave de la base)
import sys                            # salida de la consola y cierre del programa con error
import warnings                       # permite ocultar un aviso de pandas que no aplica
from datetime import date, timedelta  # fechas y diferencias entre fechas
from pathlib import Path              # rutas de carpetas y archivos (funciona en Windows y Linux)

# --- matplotlib: gráficos ---
import matplotlib
# 'Agg' dibuja en memoria sin abrir ninguna ventana: el script solo guarda
# los PNG. Tiene que ir ANTES de importar pyplot.
matplotlib.use('Agg')

import matplotlib.pyplot as plt          # funciones para crear figuras y gráficos
import numpy as np                       # cálculo numérico (sumas, promedios, percentiles, tendencia)
import pandas as pd                      # tablas de datos (DataFrame): leer, agrupar, pivotear
from matplotlib.gridspec import GridSpec # grilla para ubicar varios gráficos en el dashboard

# --- Conexión a la base ---
import MySQLdb                  # conector nativo de MySQL (paquete mysqlclient)
from dotenv import load_dotenv  # lee el archivo .env con las credenciales

# pandas avisa que prefiere SQLAlchemy; con el conector nativo funciona igual,
# así que se oculta ese aviso para que la salida de la terminal quede limpia.
warnings.filterwarnings('ignore', message='.*pandas only supports SQLAlchemy.*')


# ============================================================
# CONSTANTES
# ============================================================

# Carpeta raíz del proyecto: este archivo está en analitica/, se sube un nivel.
RAIZ = Path(__file__).resolve().parent.parent

# Zona horaria de la Argentina (la misma de settings.TIME_ZONE en Django).
# La base guarda las fechas y horas en UTC; con esto se pasan a hora local.
ZONA = 'America/Argentina/Buenos_Aires'

# Nombres de los tipos de movimiento que cuentan como egreso por venta y
# como egreso por vencimiento de lote.
TIPOS_VENTA = ('Egreso por venta', 'Salida por venta')
TIPO_BAJA = 'Salida por vencimiento de producto'

# Las tres categorías que se comparan en los gráficos 1 y 3.
CATEGORIAS = ['Ingresos de lotes', 'Egresos por venta', 'Egresos por vencimiento']

# Paleta de colores (códigos hexadecimales). Para cambiar un color,
# alcanza con cambiarlo acá: todos los gráficos lo toman de estas variables.
VERDE, VERDE_OSC, VERDE_CLARO = '#2E9E57', '#1E6B3A', '#BFE8C9'
AZUL, ROJO, NARANJA, GRIS = '#2F6DB5', '#D64545', '#F2A71B', '#9AA5A0'

# Un color por categoría, el mismo en todos los gráficos:
#   azul = entra mercadería, verde = se vende, rojo = se pierde.
COLOR_CATEGORIA = {
    'Ingresos de lotes': AZUL,
    'Egresos por venta': VERDE,
    'Egresos por vencimiento': ROJO,
}

# Colores del donut, en orden: uno por porción.
# Azul petróleo, verde agua, mostaza, durazno, terracota y gris para "Otros".
COLORES = ['#264653', '#2A9D8F', '#E9C46A', '#F4A261', '#E76F51', GRIS]

# Mapa de colores del heatmap (de amarillo claro a azul oscuro).
MAPA_CALOR = 'YlGnBu'

# Equivalencia entre la opción --agrupar y el código de frecuencia de pandas:
#   'D'     = diario
#   'W-MON' = semanal, empezando el lunes
#   'MS'    = mensual, con la fecha del primer día del mes (Month Start)
FRECUENCIAS = {'dia': 'D', 'semana': 'W-MON', 'mes': 'MS'}

# Nombres en castellano para los ejes de los gráficos.
DIAS_ES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
MESES_ES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
            'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


# ============================================================
# PARÁMETROS
# Lee lo que se escribe después de "python analitica/analitica.py"
# ============================================================

def leer_parametros():
    hoy = date.today()

    # ArgumentParser arma el menú de parámetros (y el --help automático).
    p = argparse.ArgumentParser(description='Analítica de Agroquímica del Valle')

    # type=date.fromisoformat convierte el texto "2026-10-25" en una fecha.
    # Si no se indica, el rango por defecto es el último año hasta hoy.
    p.add_argument('--desde', type=date.fromisoformat, default=hoy - timedelta(days=365))
    p.add_argument('--hasta', type=date.fromisoformat, default=hoy)

    # choices: solo acepta 'dia', 'semana' o 'mes' (las claves de FRECUENCIAS).
    p.add_argument('--agrupar', choices=FRECUENCIAS, default='mes')

    # Filtros opcionales: si no se escriben, quedan en None (sin filtro).
    p.add_argument('--tipo', default=None, help='Tipo de producto (nombre)')
    p.add_argument('--proveedor', default=None, help='Proveedor del remito (nombre)')

    # Cuántos productos muestra el donut; el resto se junta en "Otros".
    p.add_argument('--top', type=int, default=5)

    # Carpeta donde se guardan las imágenes y el CSV.
    p.add_argument('--salida', type=Path, default=RAIZ / 'analitica' / 'salida')

    args = p.parse_args()

    # Validaciones: p.error() muestra el mensaje y corta el programa.
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
    # Carga las variables del archivo .env (DB_HOST, DB_USER, ...) en el entorno.
    load_dotenv(RAIZ / '.env')

    # Abre la conexión a MySQL. Si alguna variable falta, se usa el valor
    # por defecto (servidor local 127.0.0.1, puerto 3306).
    return MySQLdb.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        port=int(os.getenv('DB_PORT') or 3306),
        user=os.getenv('DB_USER'),
        passwd=os.getenv('DB_PASSWORD'),
        db=os.getenv('DB_NAME'),
        charset='utf8mb4',   # para leer bien acentos y la ñ
    )


# ------------------------------------------------------------
# CONSULTAS SQL
# Los %s son parámetros: las fechas se pasan aparte (params=...) y no se
# escriben dentro del texto del SQL. Así se evita la inyección SQL.
# ------------------------------------------------------------

# Egresos por venta, egresos por vencimiento y demás movimientos de stock
# (no anulados) del período.
# Une el movimiento con su tipo, su lote, el remito del lote, el proveedor
# del remito, el producto y el tipo de producto.
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

# Ingresos de lotes: lotes ingresados en el período por remitos confirmados
# (mismo criterio que el reporte consolidado de M2).
# Los remitos anulados no cuentan como ingreso.
SQL_INGRESOS = """
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
# DISTINCT: cada par producto-proveedor aparece una sola vez.
SQL_PRODUCTOS_PROVEEDOR = """
    SELECT  DISTINCT l.ID_Producto AS producto_id, pr.nombre_proveedor AS proveedor
    FROM    LOTES l
    JOIN    REMITOS r       ON r.ID_Remito = l.ID_Remito
    JOIN    PROVEEDORES pr  ON pr.ID_Proveedor = r.ID_Proveedor
    WHERE   r.Estado_remito = 'Confirmado'
"""

# Stock actual de los productos activos (para el stock valorizado y los
# productos en stock mínimo).
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
    # Ejemplo: el 25/10 a las 00:00 de Argentina son las 03:00 en UTC.
    # tz_localize(None) quita la zona para compararla con la columna de MySQL.
    inicio = pd.Timestamp(args.desde, tz=ZONA).tz_convert('UTC').tz_localize(None)
    # Se suma un día al "hasta" para incluir ese día completo (hasta las 23:59).
    fin = pd.Timestamp(args.hasta + timedelta(days=1), tz=ZONA).tz_convert('UTC').tz_localize(None)

    # pd.read_sql ejecuta la consulta y devuelve un DataFrame (una tabla de
    # pandas). params reemplaza los %s del SQL, en orden.
    mov = pd.read_sql(SQL_MOVIMIENTOS, conn,
                      params=[inicio.to_pydatetime(), fin.to_pydatetime()])
    ingresos = pd.read_sql(SQL_INGRESOS, conn, params=[args.desde, args.hasta])
    prov = pd.read_sql(SQL_PRODUCTOS_PROVEEDOR, conn)
    stock = pd.read_sql(SQL_STOCK, conn)

    return preparar(mov, ingresos, prov, stock, args)


def preparar(mov, ingresos, prov, stock, args):
    """Tipos de datos, categorías de negocio y filtros (pandas)."""
    # UTC -> hora local de la Argentina.
    # to_datetime: valor de MySQL -> fecha de pandas.
    # tz_localize('UTC'): indica que esa hora está en UTC.
    # tz_convert(ZONA): la pasa a la hora de Buenos Aires.
    # tz_localize(None): le quita la zona para trabajar más simple.
    mov['fecha_hora'] = (pd.to_datetime(mov['fecha_hora'])
                         .dt.tz_localize('UTC').dt.tz_convert(ZONA).dt.tz_localize(None))
    # Fecha_ingreso es un DATE (sin hora): no se convierte de zona.
    ingresos['fecha'] = pd.to_datetime(ingresos['fecha'])

    # MySQL devuelve los precios como Decimal; se pasan a float para poder
    # hacer cuentas con numpy.
    for df in (mov, stock):
        df['precio'] = df['precio'].astype(float)
    for df in (mov, ingresos, stock):
        if 'cantidad' in df:
            df['cantidad'] = df['cantidad'].astype(float)

    # Categoría de negocio de cada movimiento.
    # np.select evalúa las condiciones en orden y asigna el valor de la
    # primera que se cumple: venta -> 'Egresos por venta', vencimiento ->
    # 'Egresos por vencimiento', cualquier otro movimiento -> 'Otros'.
    mov['categoria'] = np.select(
        [mov['tipo_movimiento'].isin(TIPOS_VENTA),
         mov['tipo_movimiento'] == TIPO_BAJA],
        ['Egresos por venta', 'Egresos por vencimiento'],
        default='Otros',
    )

    # ---- Filtros ----
    # df[condición] deja solo las filas donde la condición es verdadera.
    if args.tipo:
        mov = mov[mov['tipo_producto'] == args.tipo]
        ingresos = ingresos[ingresos['tipo_producto'] == args.tipo]
        stock = stock[stock['tipo_producto'] == args.tipo]
    if args.proveedor:
        mov = mov[mov['proveedor'] == args.proveedor]
        ingresos = ingresos[ingresos['proveedor'] == args.proveedor]
        # El stock no tiene proveedor: se filtra por los productos que ese
        # proveedor entregó alguna vez (isin = "está en la lista").
        ids = prov.loc[prov['proveedor'] == args.proveedor, 'producto_id'].unique()
        stock = stock[stock['producto_id'].isin(ids)]

    # reset_index renumera las filas 0, 1, 2... después de filtrar.
    return (mov.reset_index(drop=True), ingresos.reset_index(drop=True),
            stock.reset_index(drop=True))


# ============================================================
# INDICADORES (numpy)
# Los números que se muestran en la terminal y en las tarjetas del dashboard.
# ============================================================

def indicadores(mov, ingresos, stock):
    # Solo los egresos por venta.
    egresos_venta = mov[mov['categoria'] == 'Egresos por venta']

    # to_numpy convierte la columna de pandas en un arreglo de numpy.
    cant = egresos_venta['cantidad'].to_numpy(dtype=float)

    # Facturación = suma de (cantidad × precio) de cada egreso por venta.
    facturacion = float(np.sum(cant * egresos_venta['precio'].to_numpy(dtype=float)))

    # Total de unidades ingresadas en lotes en el período.
    ingresado = float(np.sum(ingresos['cantidad'].to_numpy(dtype=float)))

    # Total de unidades egresadas por vencimiento de lote.
    vencido = float(np.sum(mov.loc[mov['categoria'] == 'Egresos por vencimiento', 'cantidad']))

    # Cada indicador tiene "if cant.size else 0" para no fallar si no hay
    # egresos por venta (por ejemplo, con un filtro que no trae datos).
    return {
        'unidades_egresadas': int(np.sum(cant)) if cant.size else 0,
        'facturacion': facturacion,
        'egresos': int(cant.size),                                           # cantidad de egresos por venta
        'media_egreso': float(np.mean(cant)) if cant.size else 0.0,          # promedio por egreso
        'mediana_egreso': float(np.median(cant)) if cant.size else 0.0,      # valor del medio
        'desvio_egreso': float(np.std(cant)) if cant.size else 0.0,          # cuánto varían
        'p90_egreso': float(np.percentile(cant, 90)) if cant.size else 0.0,  # el 90 % de los egresos es de esto o menos
        'ingresado': ingresado,
        # Porcentaje de lo ingresado que se perdió por vencimiento.
        'pct_perdida': float(np.round(vencido * 100 / ingresado, 1)) if ingresado else 0.0,
        # Valor del stock actual = suma de (stock × precio).
        'stock_valorizado': float(np.sum(stock['stock'].to_numpy(dtype=float)
                                         * stock['precio'].to_numpy(dtype=float))),
        # Cuenta los productos con stock en el mínimo o por debajo
        # (True cuenta como 1 y False como 0 al sumar).
        'en_minimo': int(np.sum(stock['stock'].to_numpy() <= stock['minimo'].to_numpy())),
    }


def pesos(valor):
    """Formato de pesos argentino: 4450168 -> '$ 4.450.168'."""
    return '$ ' + f'{valor:,.0f}'.replace(',', '.')


# ============================================================
# TRANSFORMACIONES (pandas)
# Arman las tablas que necesita cada gráfico.
# ============================================================

def etiqueta_periodo(ts, agrupar):
    """Texto del eje X: 'Oct 26' si es por mes, '25/10' si es por día o semana."""
    if agrupar == 'mes':
        return f'{MESES_ES[ts.month - 1]} {str(ts.year)[2:]}'
    return ts.strftime('%d/%m')


def serie_por_categoria(mov, ingresos, args):
    """concat + pivot_table + resample: unidades por período y categoría.

    Resultado: una tabla con una fila por período (día, semana o mes) y
    una columna por categoría (Ingresos de lotes, Egresos por venta,
    Egresos por vencimiento).
    La usan los gráficos 1 (barras) y 3 (tendencia).
    """
    freq = FRECUENCIAS[args.agrupar]

    # pd.concat une dos tablas una debajo de la otra:
    #   - los egresos por venta y por vencimiento, con su fecha y cantidad;
    #   - los lotes ingresados, a los que se les agrega la categoría
    #     'Ingresos de lotes'.
    # Las dos quedan con las mismas tres columnas.
    datos = pd.concat([
        mov.loc[mov['categoria'].isin(CATEGORIAS), ['fecha_hora', 'categoria', 'cantidad']],
        ingresos.assign(fecha_hora=ingresos['fecha'], categoria='Ingresos de lotes')
               [['fecha_hora', 'categoria', 'cantidad']],
    ], ignore_index=True)

    # pivot_table: filas = fecha, columnas = categoría, valores = suma de
    # unidades. Es la misma técnica que el ejemplo del parcial.
    tabla = datos.pivot_table(index='fecha_hora', columns='categoria',
                              values='cantidad', aggfunc='sum')
    if not tabla.empty:
        # resample agrupa las fechas en períodos (día, semana o mes) y suma.
        # label/closed='left': cada período queda con la fecha en que EMPIEZA
        # (con semanas, el lunes de esa semana). Si no, la última semana
        # quedaría con una fecha posterior a --hasta y se perdería.
        tabla = tabla.resample(freq, label='left', closed='left').sum()

    # Todos los períodos del rango, aunque no tengan movimientos, para que
    # el eje X no tenga huecos (los períodos vacíos quedan en 0).
    inicio = pd.Timestamp(args.desde)
    if args.agrupar == 'mes':
        inicio = inicio.replace(day=1)                          # primer día del mes
    elif args.agrupar == 'semana':
        inicio = inicio - pd.Timedelta(days=inicio.weekday())   # lunes de esa semana
    periodos = pd.date_range(inicio, pd.Timestamp(args.hasta), freq=freq)
    tabla = tabla.reindex(periodos, fill_value=0)

    # Si una categoría no tuvo ningún dato, se crea la columna en 0.
    for c in CATEGORIAS:
        if c not in tabla:
            tabla[c] = 0
    # Columnas siempre en el mismo orden; fillna(0) reemplaza los vacíos.
    return tabla[CATEGORIAS].fillna(0)


def facturacion_por_producto(mov, top):
    """Facturación de cada producto, de mayor a menor (para el donut)."""
    # .copy() evita modificar la tabla original al agregar la columna.
    egresos_venta = mov[mov['categoria'] == 'Egresos por venta'].copy()
    egresos_venta['importe'] = egresos_venta['cantidad'] * egresos_venta['precio']

    # groupby: suma el importe de cada producto; sort_values: ordena de mayor a menor.
    serie = egresos_venta.groupby('producto')['importe'].sum().sort_values(ascending=False)

    # Si hay más productos que el top, los primeros quedan y el resto se
    # suma en una sola porción llamada "Otros".
    if len(serie) > top:
        serie = pd.concat([serie.iloc[:top], pd.Series({'Otros': serie.iloc[top:].sum()})])

    # Se descartan los productos con facturación 0.
    return serie[serie > 0]


def matriz_dia_hora(mov):
    """Cantidad de movimientos por día de la semana (filas) y hora (columnas)."""
    # dt.day_of_week: 0 = lunes ... 6 = domingo. dt.hour: la hora (0 a 23).
    df = mov.assign(dia=mov['fecha_hora'].dt.day_of_week, hora=mov['fecha_hora'].dt.hour)

    # pivot_table con aggfunc='count': cuenta cuántos movimientos hubo en
    # cada combinación de día y hora.
    mat = df.pivot_table(index='dia', columns='hora', values='id', aggfunc='count')

    # Columnas del heatmap: de 7 a 21 h como mínimo (horario ampliado). Si
    # hubo movimientos antes o después, el rango se estira para incluirlos.
    horas = range(7, 22)   # horario de atención ampliado
    if not mat.empty:
        horas = range(min(7, int(mat.columns.min())), max(21, int(mat.columns.max())) + 1)

    # reindex: asegura los 7 días y todas las horas; los vacíos quedan en 0.
    return mat.reindex(index=range(7), columns=list(horas)).fillna(0)


# ============================================================
# GRÁFICOS (matplotlib)
# Cada función recibe un "ax" (el área donde se dibuja) para poder usarla
# tanto en su imagen individual como dentro del dashboard.
# ============================================================

def estilo_ejes(ax, titulo):
    """Estilo común: título verde, sin bordes de arriba y derecha, grilla suave."""
    ax.set_title(titulo, color=VERDE_OSC, fontweight='bold', fontsize=12)
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='y', linestyle='--', alpha=0.35)


def sin_datos(ax, texto='Sin datos para los filtros elegidos'):
    """Mensaje en el centro del gráfico cuando no hay datos para mostrar."""
    # transform=ax.transAxes: las coordenadas van de 0 a 1 dentro del gráfico,
    # así (0.5, 0.5) es siempre el centro.
    ax.text(0.5, 0.5, texto, ha='center', va='center', color='gray',
            transform=ax.transAxes, fontsize=11)
    ax.set_xticks([])
    ax.set_yticks([])


def g1_barras_agrupadas(tabla, args, ax):
    """1. Comparativo categórico: ingresos de lotes y egresos por período."""
    estilo_ejes(ax, 'Ingresos de lotes, egresos por venta y por vencimiento (unidades)')
    if tabla.to_numpy().sum() == 0:
        return sin_datos(ax)

    # x = posición de cada período en el eje (0, 1, 2, ...).
    x = np.arange(len(tabla))
    ancho = 0.27   # ancho de cada barra (3 barras por período ≈ 0.81)

    # Una serie de barras por categoría, corridas a la izquierda, al centro y
    # a la derecha de cada período: (i - 1) vale -1, 0 y 1.
    for i, col in enumerate(tabla.columns):
        barras = ax.bar(x + (i - 1) * ancho, tabla[col], ancho, label=col,
                        color=COLOR_CATEGORIA[col])
        # Número encima de cada barra (vacío si la barra vale 0).
        ax.bar_label(barras, labels=[f'{v:.0f}' if v else '' for v in tabla[col]],
                     fontsize=7, padding=2)

    # Etiquetas del eje X; se inclinan 45° si hay más de 12 períodos.
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

    # ax.pie dibuja el gráfico de torta:
    #   autopct    -> texto con el % dentro de cada porción.
    #   startangle -> empieza arriba (90°).
    #   wedgeprops width=0.42 -> deja el centro hueco: por eso es un "donut".
    porciones, textos, pct = ax.pie(
        serie.to_numpy(), labels=etiquetas, colors=colores,
        autopct=lambda p: f'{p:.1f}%' if p >= MINIMO else '',
        startangle=90, pctdistance=0.78,
        wedgeprops={'width': 0.42, 'edgecolor': 'white'},
    )

    if con_leyenda:
        # Leyenda a la derecha: "Producto (12,5%)".
        ax.legend(
            porciones,
            [f'{n} ({p:.1f}%)'.replace('.', ',') for n, p in zip(serie.index, porcentajes)],
            loc='center left', bbox_to_anchor=(1.02, 0.5),
            fontsize=7, frameon=False,
        )

    # Porcentajes en blanco y negrita, para que se lean sobre el color.
    for t in pct:
        t.set_color('white')
        t.set_fontweight('bold')
        t.set_fontsize(8)

    # Total facturado escrito en el centro del donut.
    ax.text(0, 0, pesos(serie.sum()), ha='center', va='center',
            fontweight='bold', color=VERDE_OSC, fontsize=11)
    ax.axis('equal')   # círculo redondo, no ovalado


def g3_tendencia(tabla, args, ax):
    """3. Evolución temporal: egresos por venta con media móvil y tendencia."""
    estilo_ejes(ax, 'Evolución de los egresos por venta (unidades)')
    egresos_venta = tabla['Egresos por venta'].astype(float)
    if egresos_venta.sum() == 0:
        return sin_datos(ax)

    x = np.arange(len(egresos_venta))     # posición de cada período
    y = egresos_venta.to_numpy()          # unidades egresadas por venta en cada período
    media = float(np.mean(y))      # promedio de todos los períodos

    # Línea principal: unidades egresadas por venta en cada período.
    ax.plot(x, y, marker='o', color=VERDE, linewidth=2, label='Egresos por venta')

    # Media móvil: promedio de los últimos 3 períodos (suaviza los picos).
    # min_periods=1 permite calcularla desde el primer período.
    ax.plot(x, egresos_venta.rolling(3, min_periods=1).mean(), color=AZUL, linestyle=':',
            linewidth=2, label='Media móvil (3 períodos)')

    # Recta de tendencia: np.polyfit(x, y, 1) ajusta una recta y = a·x + b
    # por mínimos cuadrados. La pendiente "a" dice cuántas unidades suben
    # (+) o bajan (−) los egresos por venta por período. Hacen falta al menos 2 puntos.
    if len(x) >= 2:
        pendiente, ordenada = np.polyfit(x, y, 1)
        ax.plot(x, pendiente * x + ordenada, color=NARANJA, linestyle='--',
                label=f'Tendencia ({pendiente:+.1f} u. por período)')

    # Línea horizontal en el promedio.
    ax.axhline(media, color=GRIS, linewidth=1)

    # fill_between pinta el área entre la línea de egresos y el promedio:
    # verde donde se vendió más que el promedio, rojo donde se vendió menos.
    # interpolate=True hace que el cambio de color sea justo donde se cruzan.
    ax.fill_between(x, y, media, where=y >= media, interpolate=True,
                    color=VERDE_CLARO, alpha=0.5, label='Sobre el promedio')
    ax.fill_between(x, y, media, where=y < media, interpolate=True,
                    color='#F6C1C1', alpha=0.5, label='Debajo del promedio')

    ax.set_xticks(x, [etiqueta_periodo(t, args.agrupar) for t in egresos_venta.index],
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

    # imshow dibuja la matriz como una grilla de colores con la escala
    # MAPA_CALOR: cuanto más alto el valor, más oscuro (de amarillo a azul).
    im = ax.imshow(valores, cmap=MAPA_CALOR, aspect='auto')

    # Barra de referencia de colores a la derecha.
    fig.colorbar(im, ax=ax, label='N° de movimientos')

    # Nombres de los ejes: días en las filas, horas en las columnas.
    ax.set_yticks(range(7), DIAS_ES)
    ax.set_xticks(range(len(mat.columns)), [f'{h:02d}:00' for h in mat.columns],
                  rotation=45, fontsize=8)

    # Escribe el número dentro de cada cuadro con movimientos. Si el cuadro
    # es oscuro (más del 60 % del máximo), el número va en blanco para que
    # se lea; si es claro, en negro.
    umbral = valores.max() * 0.6
    for i in range(valores.shape[0]):          # recorre los días (filas)
        for j in range(valores.shape[1]):      # recorre las horas (columnas)
            if valores[i, j]:
                ax.text(j, i, int(valores[i, j]), ha='center', va='center', fontsize=8,
                        color='white' if valores[i, j] > umbral else '#1c2a23')


def guardar(fig, carpeta, nombre):
    """Guarda la figura como PNG, la cierra y muestra la ruta en la terminal."""
    ruta = carpeta / nombre
    # dpi=150: buena resolución; bbox_inches='tight': recorta los márgenes blancos.
    fig.savefig(ruta, dpi=150, bbox_inches='tight')
    plt.close(fig)   # libera la memoria de la figura
    print(f'  ✓ {ruta}')
    return ruta


def subtitulo(args):
    """Texto con el período y los filtros usados, ej. '25/10/2026 al 08/11/2026 · Tipo: X'."""
    partes = [f'{args.desde:%d/%m/%Y} al {args.hasta:%d/%m/%Y}']
    if args.tipo:
        partes.append(f'Tipo: {args.tipo}')
    if args.proveedor:
        partes.append(f'Proveedor: {args.proveedor}')
    return ' · '.join(partes)


def dashboard(tabla, serie, mat, kpi, args, carpeta):
    """5. Panel integrado (GridSpec): KPIs + gráficos principales."""
    fig = plt.figure(figsize=(16, 10))   # tamaño en pulgadas

    # Grilla de 3 filas × 4 columnas:
    #   fila 0 (baja): las 4 tarjetas de indicadores;
    #   filas 1 y 2 (altas): los gráficos.
    # hspace/wspace: separación entre filas y columnas.
    gs = GridSpec(3, 4, figure=fig, height_ratios=[0.55, 2, 2], hspace=0.55, wspace=0.35)
    fig.suptitle(f'Dashboard ejecutivo · Agroquímica del Valle\n{subtitulo(args)}',
                 color=VERDE_OSC, fontweight='bold', fontsize=15)

    # Tarjetas: (título, valor ya formateado).
    tarjetas = [
        ('Unidades egresadas por venta', f'{kpi["unidades_egresadas"]:,}'.replace(',', '.')),
        ('Facturación estimada', pesos(kpi['facturacion'])),
        ('Egresos por vencimiento\n(% de lo ingresado)', f'{kpi["pct_perdida"]:.1f} %'.replace('.', ',')),
        ('Stock valorizado', pesos(kpi['stock_valorizado'])),
    ]
    for i, (titulo, valor) in enumerate(tarjetas):
        ax = fig.add_subplot(gs[0, i])   # fila 0, columna i
        ax.axis('off')                   # sin ejes: es solo una tarjeta
        # Fondo verde claro que ocupa toda la tarjeta.
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                                   color='#eaf4e6', zorder=0))
        # va='center' centra el título aunque ocupe dos renglones (\n).
        ax.text(0.5, 0.74, titulo, ha='center', va='center', color='#4a5a52', fontsize=10,
                transform=ax.transAxes)
        ax.text(0.5, 0.26, valor, ha='center', va='center', color=VERDE_OSC, fontsize=15,
                fontweight='bold', transform=ax.transAxes)

    # Ubicación de cada gráfico en la grilla (gs[fila, columnas]):
    g1_barras_agrupadas(tabla, args, fig.add_subplot(gs[1, :3]))  # fila 1, columnas 0 a 2
    g2_donut(serie, fig.add_subplot(gs[1, 3]))                     # fila 1, columna 3
    g3_tendencia(tabla, args, fig.add_subplot(gs[2, :2]))          # fila 2, columnas 0 y 1
    g4_heatmap(mat, fig.add_subplot(gs[2, 2:]), fig)               # fila 2, columnas 2 y 3

    return guardar(fig, carpeta, '5_dashboard_ejecutivo.png')


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def generar(mov, ingresos, stock, args):
    """Indicadores, transformaciones y gráficos a partir de los datos leídos."""
    # Cantidad de filas leídas de cada consulta.
    print(f'Movimientos leídos: {len(mov)} · Lotes ingresados: {len(ingresos)} · '
          f'Productos con stock: {len(stock)}')

    # --- 1. Indicadores (numpy) y su impresión en la terminal ---
    kpi = indicadores(mov, ingresos, stock)
    print('\nIndicadores (numpy):')
    print(f'  Unidades egresadas venta . {kpi["unidades_egresadas"]}')
    print(f'  Facturación estimada ..... {pesos(kpi["facturacion"])}')
    print(f'  Egresos por venta ........ {kpi["egresos"]}')
    print(f'  Egreso medio / mediana ... {kpi["media_egreso"]:.1f} / {kpi["mediana_egreso"]:.1f} u.')
    print(f'  Desvío estándar egreso ... {kpi["desvio_egreso"]:.1f} u. (P90: {kpi["p90_egreso"]:.1f})')
    print(f'  Unidades ingresadas lotes  {kpi["ingresado"]:.0f}')
    print(f'  Pérdida por vencimiento .. {kpi["pct_perdida"]:.1f} % de lo ingresado')
    print(f'  Stock valorizado ......... {pesos(kpi["stock_valorizado"])}')
    print(f'  Productos en stock mínimo  {kpi["en_minimo"]}')

    # --- 2. Tablas para los gráficos (pandas) ---
    tabla = serie_por_categoria(mov, ingresos, args)   # gráficos 1 y 3
    serie = facturacion_por_producto(mov, args.top)   # gráfico 2
    mat = matriz_dia_hora(mov)                        # gráfico 4

    # --- 3. Gráficos individuales (matplotlib) ---
    # Cada uno: crear la figura, dibujar, poner el subtítulo con los
    # filtros abajo y guardar el PNG.
    print('\nGráficos generados:')

    fig, ax = plt.subplots(figsize=(12, 5))
    g1_barras_agrupadas(tabla, args, ax)
    fig.suptitle(subtitulo(args), fontsize=9, color='gray', y=0.02)
    guardar(fig, args.salida, '1_ingresos_y_egresos.png')

    fig, ax = plt.subplots(figsize=(7, 7))
    g2_donut(serie, ax)
    fig.suptitle(subtitulo(args), fontsize=9, color='gray', y=0.06)
    guardar(fig, args.salida, '2_participacion_facturacion.png')

    fig, ax = plt.subplots(figsize=(12, 5))
    g3_tendencia(tabla, args, ax)
    fig.suptitle(subtitulo(args), fontsize=9, color='gray', y=0.02)
    guardar(fig, args.salida, '3_evolucion_egresos_venta.png')

    fig, ax = plt.subplots(figsize=(12, 4.5))
    g4_heatmap(mat, ax, fig)
    fig.suptitle(subtitulo(args), fontsize=9, color='gray', y=0.0)
    guardar(fig, args.salida, '4_heatmap_dia_hora.png')

    # --- 4. Dashboard con todo junto ---
    dashboard(tabla, serie, mat, kpi, args, args.salida)

    # --- 5. Tabla resumen para el informe (se abre con Excel) ---
    resumen = tabla.copy()
    resumen.index = [etiqueta_periodo(t, args.agrupar) for t in resumen.index]
    # utf-8-sig: para que Excel muestre bien los acentos.
    resumen.to_csv(args.salida / 'resumen_por_periodo.csv', encoding='utf-8-sig')
    print(f'  ✓ {args.salida / "resumen_por_periodo.csv"}')


def main():
    # La consola de Windows usa cp1252: se fuerza UTF-8 para los acentos y el ✓.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    # 1. Parámetros y carpeta de salida (se crea si no existe).
    args = leer_parametros()
    args.salida.mkdir(parents=True, exist_ok=True)

    print(f'Analítica · {subtitulo(args)} · agrupado por {args.agrupar}')

    # 2. Conexión: si falla (MySQL apagado, .env mal), se muestra el error y se corta.
    try:
        conn = conectar()
    except MySQLdb.Error as e:
        sys.exit(f'No se pudo conectar a la base de datos: {e}')

    # 3. Lectura de los datos. finally: la conexión se cierra siempre,
    #    aunque haya un error en la lectura.
    try:
        mov, ingresos, stock = leer_datos(conn, args)
    finally:
        conn.close()

    # 4. Indicadores, gráficos y CSV.
    generar(mov, ingresos, stock, args)


# Solo se ejecuta main() cuando se corre este archivo directamente
# (python analitica/analitica.py), no cuando otro archivo lo importa.
if __name__ == '__main__':
    main()
    