"""
PDF de los reportes consolidados · Agroquímica del Valle  (Parcial 2 - M2)

Mismo estilo que el PDF del remito: banda verde con degradado y el logo,
línea amarilla, recuadros redondeados y pie con línea fina.

A4 apaisado con:
  - Encabezado institucional en cada hoja (logo, título del reporte,
    procesos que cruza y fecha de emisión).
  - En la primera hoja, recuadros con los filtros aplicados, el usuario
    que lo emitió y la fecha y hora.
  - La grilla completa (todas las filas, no solo la página en pantalla)
    con la fila de totales al final.
  - Pie en cada hoja con los filtros aplicados, el usuario que lo emitió,
    la fecha y hora de emisión y el número de página.

Uso:
    pdf = generar_pdf_consolidado(reporte, filas, totales, texto_filtros,
                                  usuario_texto, emitido, logo_path)
"""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .consolidados import fila_totales, filas_formateadas

# Colores de la agroquímica (los mismos del PDF del remito)
VERDE = colors.HexColor('#185a38')
VERDE_OSCURO = colors.HexColor('#0f3a24')
VERDE_MEDIO = colors.HexColor('#2e7d32')
VERDE_CLARO = colors.HexColor('#eaf4e6')
VERDE_FILA = colors.HexColor('#f6fbf4')
AMARILLO = colors.HexColor('#f5c400')
BORDE = colors.HexColor('#d6e6d4')
LINEA_FILA = colors.HexColor('#e4efe2')
TEXTO = colors.HexColor('#1c2a23')
SUAVE = colors.HexColor('#6b7c73')
CLARO_BANDA = colors.HexColor('#d9efe0')
ROJO = colors.HexColor('#b91c1c')

ANCHO, ALTO = landscape(A4)
MARGEN = 1.4 * cm
ALTO_ENCABEZADO = 3.0 * cm
ALTO_PIE = 1.7 * cm


def _estilo(nombre, **kw):
    base = {'fontName': 'Helvetica', 'fontSize': 8.5, 'leading': 11, 'textColor': TEXTO}
    base.update(kw)
    return ParagraphStyle(nombre, **base)


E_CELDA = _estilo('celda')
E_CELDA_D = _estilo('celda_d', alignment=TA_RIGHT)
E_CELDA_C = _estilo('celda_c', alignment=TA_CENTER)
E_CAB = _estilo('cab', fontName='Helvetica-Bold', fontSize=7.5, leading=9,
                textColor=colors.white, alignment=TA_CENTER)
E_TOTAL = _estilo('total', fontName='Helvetica-Bold', textColor=VERDE_OSCURO)
E_TOTAL_C = _estilo('total_c', fontName='Helvetica-Bold', textColor=VERDE_OSCURO,
                    alignment=TA_CENTER)
E_TOTAL_D = _estilo('total_d', fontName='Helvetica-Bold', textColor=VERDE_OSCURO,
                    alignment=TA_RIGHT)
E_TITULO = _estilo('titulo', fontName='Helvetica-Bold', fontSize=14, leading=17,
                   textColor=VERDE)
E_DESC = _estilo('desc', fontSize=8.5, leading=11.5, textColor=SUAVE)
E_ETIQUETA = _estilo('etiqueta', fontName='Helvetica-Bold', fontSize=7, leading=9,
                     textColor=SUAVE)
E_VALOR = _estilo('valor', fontName='Helvetica-Bold', fontSize=9, leading=11.5)
E_TITULO_CAJA = _estilo('titulo_caja', fontName='Helvetica-Bold', fontSize=8,
                        leading=10, textColor=VERDE)
E_PIE = _estilo('pie', fontSize=7, leading=9, textColor=SUAVE)
E_SENSIBLE = _estilo('sensible', fontName='Helvetica-Bold', fontSize=7.5, leading=9,
                     textColor=ROJO)

DERECHA = ('entero', 'moneda', 'pct')


def _celda(texto, formato, total=False):
    # Todo centrado bajo su encabezado, igual que la grilla en pantalla.
    return Paragraph(escape(texto), E_TOTAL_C if total else E_CELDA_C)


def _caja(etiqueta, valor, ancho):
    """Recuadro con etiqueta chica y valor (como las cajas del remito)."""
    tabla = Table(
        [[Paragraph(escape(etiqueta), E_ETIQUETA)], [Paragraph(escape(valor), E_VALOR)]],
        colWidths=[ancho],
    )
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), VERDE_FILA),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDE),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 1), (-1, 1), 1),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 7),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    return tabla


def _dibujar_encabezado(c, reporte, emitido, logo_path):
    """Banda verde con degradado, logo, título del reporte y fecha."""
    y_banda = ALTO - ALTO_ENCABEZADO

    c.saveState()
    ruta = c.beginPath()
    ruta.rect(0, y_banda, ANCHO, ALTO_ENCABEZADO)
    c.clipPath(ruta, stroke=0, fill=0)
    c.linearGradient(0, y_banda, ANCHO, ALTO, (VERDE_OSCURO, VERDE_MEDIO))

    # Círculos decorativos
    c.setFillColor(colors.white)
    c.setFillAlpha(0.06)
    c.circle(ANCHO * 0.42, y_banda + 0.3 * cm, 2.6 * cm, stroke=0, fill=1)
    c.circle(ANCHO * 0.70, ALTO - 0.4 * cm, 2.0 * cm, stroke=0, fill=1)
    c.restoreState()

    c.saveState()

    # Línea amarilla bajo la banda
    c.setFillColor(AMARILLO)
    c.rect(0, y_banda - 0.12 * cm, ANCHO, 0.12 * cm, stroke=0, fill=1)

    # Logo (texto blanco y amarillo: va sobre el verde)
    dibujado = False
    if logo_path:
        try:
            imagen = ImageReader(logo_path)
            ancho_img, alto_img = imagen.getSize()
            ancho_logo = 6.6 * cm
            alto_logo = ancho_logo * alto_img / ancho_img
            c.drawImage(imagen, MARGEN - 0.2 * cm,
                        y_banda + (ALTO_ENCABEZADO - alto_logo) / 2,
                        width=ancho_logo, height=alto_logo, mask='auto')
            dibujado = True
        except Exception:
            pass

    if not dibujado:
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 16)
        c.drawString(MARGEN, y_banda + ALTO_ENCABEZADO / 2 + 0.1 * cm, 'AGROQUÍMICA')
        c.setFillColor(AMARILLO)
        c.drawString(MARGEN, y_banda + ALTO_ENCABEZADO / 2 - 0.55 * cm, 'DEL VALLE')

    # Título a la derecha
    x_der = ANCHO - MARGEN
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 17)
    c.drawRightString(x_der, ALTO - 1.05 * cm, 'REPORTE CONSOLIDADO')

    c.setFont('Helvetica', 8.5)
    c.setFillColor(CLARO_BANDA)
    c.drawRightString(x_der, ALTO - 1.55 * cm, 'Sistema de Gestión de Stock')

    # Fecha en recuadro amarillo
    texto_fecha = f'Fecha  {emitido.split(" ")[0]}'
    c.setFont('Helvetica-Bold', 8.5)
    ancho_fecha = c.stringWidth(texto_fecha, 'Helvetica-Bold', 8.5) + 0.6 * cm
    c.setFillColor(AMARILLO)
    c.roundRect(x_der - ancho_fecha, y_banda + 0.35 * cm, ancho_fecha, 0.58 * cm,
                4, stroke=0, fill=1)
    c.setFillColor(VERDE_OSCURO)
    c.drawRightString(x_der - 0.3 * cm, y_banda + 0.55 * cm, texto_fecha)

    c.restoreState()


def generar_pdf_consolidado(reporte, filas, totales, texto_filtros,
                            usuario_texto, emitido, logo_path=None):
    buffer = BytesIO()
    columnas = reporte['columnas']
    ancho = ANCHO - 2 * MARGEN - 12   # el marco de la hoja deja 6 pt de cada lado

    def encabezado_y_pie(c, doc):
        _dibujar_encabezado(c, reporte, emitido, logo_path)

        # ---------- Pie: filtros, usuario, fecha y hora, página ----------
        c.saveState()
        c.setStrokeColor(BORDE)
        c.setLineWidth(0.6)
        c.line(MARGEN, ALTO_PIE, ANCHO - MARGEN, ALTO_PIE)

        pie = Paragraph(
            f'<b>{escape(reporte["titulo"])}</b> · '
            f'<b>Filtros aplicados:</b> {escape(texto_filtros)}<br/>'
            f'<b>Emitido por:</b> {escape(usuario_texto)} · '
            f'<b>Fecha y hora:</b> {escape(emitido)} hs',
            E_PIE,
        )
        _w, h = pie.wrap(ANCHO - 2 * MARGEN - 3 * cm, ALTO_PIE)
        pie.drawOn(c, MARGEN, ALTO_PIE - 0.2 * cm - h)

        c.setFont('Helvetica-Bold', 7.5)
        c.setFillColor(VERDE)
        c.drawRightString(ANCHO - MARGEN, ALTO_PIE - 0.5 * cm, f'Página {doc.page}')
        c.restoreState()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=(ANCHO, ALTO),
        leftMargin=MARGEN,
        rightMargin=MARGEN,
        topMargin=ALTO_ENCABEZADO + 0.7 * cm,
        bottomMargin=ALTO_PIE + 0.5 * cm,
        title=reporte['titulo'],
        author='Agroquímica del Valle',
    )

    # ---------- Título, descripción y recuadros de datos ----------
    titulo = [Paragraph(escape(reporte['titulo']), E_TITULO)]
    if reporte.get('sensible'):
        titulo.append(Paragraph('REPORTE SENSIBLE · ACCESO RESTRINGIDO POR PERFIL', E_SENSIBLE))

    historia = titulo + [
        Spacer(1, 0.12 * cm),
        Paragraph(escape(reporte['descripcion']), E_DESC),
        Paragraph(f'<b>Procesos que cruza:</b> {escape(reporte["procesos"])}', E_DESC),
        Spacer(1, 0.35 * cm),
    ]

    sep = 0.3 * cm
    ancho_usuario = 8.2 * cm
    ancho_fecha = 4.2 * cm
    ancho_filtros = ancho - ancho_usuario - ancho_fecha - 2 * sep

    cajas = Table([[
        _caja('FILTROS APLICADOS', texto_filtros, ancho_filtros),
        _caja('EMITIDO POR', usuario_texto, ancho_usuario),
        _caja('FECHA Y HORA', f'{emitido} hs', ancho_fecha),
    ]], colWidths=[ancho_filtros + sep, ancho_usuario + sep, ancho_fecha])
    cajas.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    historia += [cajas, Spacer(1, 0.45 * cm)]

    # ---------- Grilla ----------
    historia += [Paragraph('DETALLE DEL REPORTE', E_TITULO_CAJA), Spacer(1, 0.18 * cm)]

    datos = [[Paragraph(escape(t), E_CAB) for _c, t, _f in columnas]]

    for fila in filas_formateadas(filas, columnas):
        datos.append([_celda(texto, fmt) for texto, fmt in fila])

    if not filas:
        datos.append([Paragraph('No hay datos para los filtros aplicados.', E_CELDA)]
                     + [''] * (len(columnas) - 1))

    datos.append([
        _celda(texto, fmt, total=True) for texto, fmt in fila_totales(totales, columnas)
    ])

    ultima = len(datos) - 1
    tabla = Table(datos, repeatRows=1, colWidths=[ancho / len(columnas)] * len(columnas))
    estilo = [
        ('BACKGROUND', (0, 0), (-1, 0), VERDE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDE),
        ('LINEBELOW', (0, 1), (-1, ultima - 1), 0.5, LINEA_FILA),
        ('BACKGROUND', (0, ultima), (-1, ultima), VERDE_CLARO),
        ('LINEABOVE', (0, ultima), (-1, ultima), 1, VERDE),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]
    for i in range(1, ultima):
        if i % 2 == 0:
            estilo.append(('BACKGROUND', (0, i), (-1, i), VERDE_FILA))
    if not filas:
        estilo.append(('SPAN', (0, 1), (-1, 1)))

    tabla.setStyle(TableStyle(estilo))
    historia.append(tabla)

    doc.build(historia, onFirstPage=encabezado_y_pie, onLaterPages=encabezado_y_pie)

    pdf = buffer.getvalue()
    buffer.close()
    return pdf
