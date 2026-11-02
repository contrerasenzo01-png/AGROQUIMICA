"""
PDF del remito con sus lotes · Agroquímica del Valle

Arma un documento A4 con la misma estructura de un remito en papel
(encabezado, datos del proveedor, detalle de la mercadería y firma de
recepción), pero solo con los datos que el sistema guarda del remito
y de sus lotes.

Uso (desde la vista):
    pdf = generar_pdf_remito(remito, lotes, registrado_por, logo_path, emitido)
"""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


# ------------------------------------------------------------
# COLORES DE LA AGROQUÍMICA
# ------------------------------------------------------------

VERDE = colors.HexColor('#185a38')
VERDE_OSCURO = colors.HexColor('#0f3a24')
VERDE_MEDIO = colors.HexColor('#2e7d32')
VERDE_CLARO = colors.HexColor('#eaf4e6')
VERDE_FILA = colors.HexColor('#f6fbf4')
AMARILLO = colors.HexColor('#f5c400')
BORDE = colors.HexColor('#d6e6d4')
TEXTO = colors.HexColor('#1c2a23')
SUAVE = colors.HexColor('#6b7c73')
ROJO = colors.HexColor('#b91c1c')
ROJO_CLARO = colors.HexColor('#fdecec')

ANCHO, ALTO = A4
MARGEN = 1.6 * cm
ALTO_ENCABEZADO = 4.2 * cm


# ------------------------------------------------------------
# ESTILOS DE TEXTO
# ------------------------------------------------------------

def _estilo(nombre, **kwargs):
    base = {
        'fontName': 'Helvetica',
        'fontSize': 9,
        'leading': 12,
        'textColor': TEXTO,
    }
    base.update(kwargs)
    return ParagraphStyle(nombre, **base)


E_ETIQUETA = _estilo('etiqueta', fontName='Helvetica-Bold', fontSize=7,
                     leading=9, textColor=SUAVE)
E_VALOR = _estilo('valor', fontName='Helvetica-Bold', fontSize=9.5, leading=12)
E_VALOR_CHICO = _estilo('valor_chico', fontSize=8.5, leading=11)
E_VALOR_ROJO = _estilo('valor_rojo', fontName='Helvetica-Bold', fontSize=9.5,
                       leading=12, textColor=ROJO)
E_TITULO_CAJA = _estilo('titulo_caja', fontName='Helvetica-Bold', fontSize=8,
                        leading=10, textColor=VERDE)
E_CELDA = _estilo('celda', fontSize=8.5, leading=11)
E_CELDA_C = _estilo('celda_c', fontSize=8.5, leading=11, alignment=TA_CENTER)
E_CELDA_D = _estilo('celda_d', fontSize=8.5, leading=11, alignment=TA_RIGHT)
E_CELDA_SUB = _estilo('celda_sub', fontSize=7, leading=9, textColor=SUAVE)
E_CAB_TABLA = _estilo('cab_tabla', fontName='Helvetica-Bold', fontSize=7.5,
                      leading=9, textColor=colors.white, alignment=TA_CENTER)
E_CAB_TABLA_I = _estilo('cab_tabla_i', fontName='Helvetica-Bold', fontSize=7.5,
                        leading=9, textColor=colors.white)
E_TOTAL = _estilo('total', fontName='Helvetica-Bold', fontSize=9, leading=11,
                  alignment=TA_RIGHT, textColor=VERDE_OSCURO)
E_TOTAL_NUM = _estilo('total_num', fontName='Helvetica-Bold', fontSize=10,
                      leading=12, alignment=TA_CENTER, textColor=VERDE_OSCURO)
E_TEXTO = _estilo('texto', fontSize=8.5, leading=12)
E_ANULADO = _estilo('anulado', fontSize=8.5, leading=12, textColor=ROJO)


# ------------------------------------------------------------
# AYUDAS DE FORMATO
# ------------------------------------------------------------

def _fecha(valor, formato='%d/%m/%Y'):
    return valor.strftime(formato) if valor else '—'


def _texto(valor, defecto='—'):
    valor = (str(valor).strip() if valor is not None else '')
    return valor or defecto


def _numero(valor):
    """Número entero con punto de miles: 1500 -> 1.500"""
    try:
        return f'{int(valor):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return '—'


def _presentacion(producto):
    """Ej.: 4 x 5 litros"""
    if not producto.Cantidad_presentacion:
        return ''

    cantidad = f'{producto.Cantidad_presentacion.normalize():f}'
    unidad = producto.Unidad_medida_producto or ''

    return f'{producto.Unidades_por_presentacion} x {cantidad} {unidad}'.strip()


def _escapar(texto):
    return (
        str(texto)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def _p(texto, estilo):
    return Paragraph(_escapar(texto), estilo)


# ------------------------------------------------------------
# ENCABEZADO Y PIE DE CADA PÁGINA
# ------------------------------------------------------------

def _dibujar_marca_anulado(c):
    """Marca de agua ANULADO, por encima del contenido de la página."""

    c.saveState()
    c.setFillColor(ROJO)
    c.setFillAlpha(0.10)
    c.setFont('Helvetica-Bold', 96)
    c.translate(ANCHO / 2, ALTO / 2 - 2 * cm)
    c.rotate(35)
    c.drawCentredString(0, 0, 'ANULADO')
    c.restoreState()


class _DocumentoRemito(SimpleDocTemplate):
    """Igual que SimpleDocTemplate, pero puede dibujar algo al terminar
    cada página (la marca de agua de los remitos anulados)."""

    def __init__(self, *args, anulado=False, **kwargs):
        self.anulado = anulado
        super().__init__(*args, **kwargs)

    def afterPage(self):
        if self.anulado:
            _dibujar_marca_anulado(self.canv)


def _dibujar_pagina(c, doc, remito, logo_path, emitido):
    """Banda verde con el logo, el título REMITO, número y fecha."""

    c.saveState()

    y_banda = ALTO - ALTO_ENCABEZADO

    # Degradado verde
    ruta = c.beginPath()
    ruta.rect(0, y_banda, ANCHO, ALTO_ENCABEZADO)
    c.clipPath(ruta, stroke=0, fill=0)
    c.linearGradient(
        0, y_banda, ANCHO, ALTO,
        (VERDE_OSCURO, VERDE_MEDIO)
    )

    # Círculos decorativos
    c.setFillColor(colors.white)
    c.setFillAlpha(0.06)
    c.circle(ANCHO * 0.42, y_banda + 0.4 * cm, 2.8 * cm, stroke=0, fill=1)
    c.circle(ANCHO * 0.70, ALTO - 0.2 * cm, 2.2 * cm, stroke=0, fill=1)
    c.restoreState()

    c.saveState()

    # Línea amarilla bajo la banda
    c.setFillColor(AMARILLO)
    c.rect(0, y_banda - 0.12 * cm, ANCHO, 0.12 * cm, stroke=0, fill=1)

    # Logo (el texto del logo es blanco y amarillo: va sobre el verde)
    if logo_path:
        try:
            imagen = ImageReader(logo_path)
            ancho_img, alto_img = imagen.getSize()
            ancho_logo = 7.2 * cm
            alto_logo = ancho_logo * alto_img / ancho_img
            c.drawImage(
                imagen,
                MARGEN - 0.2 * cm,
                y_banda + (ALTO_ENCABEZADO - alto_logo) / 2,
                width=ancho_logo,
                height=alto_logo,
                mask='auto',
            )
        except Exception:
            logo_path = None

    if not logo_path:
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 18)
        c.drawString(MARGEN, y_banda + ALTO_ENCABEZADO / 2 + 0.1 * cm, 'AGROQUÍMICA')
        c.setFillColor(AMARILLO)
        c.drawString(MARGEN, y_banda + ALTO_ENCABEZADO / 2 - 0.6 * cm, 'DEL VALLE')

    # Recuadro "R" (tipo de comprobante), como en el remito en papel
    x_r = ANCHO / 2 + 0.6 * cm
    lado_r = 1.25 * cm
    y_r = y_banda + (ALTO_ENCABEZADO - lado_r) / 2 + 0.25 * cm

    c.setFillColor(colors.white)
    c.roundRect(x_r, y_r, lado_r, lado_r, 4, stroke=0, fill=1)
    c.setFillColor(VERDE_OSCURO)
    c.setFont('Helvetica-Bold', 22)
    c.drawCentredString(x_r + lado_r / 2, y_r + 0.33 * cm, 'R')

    c.setFillColor(colors.HexColor('#d9efe0'))
    c.setFont('Helvetica', 6)
    c.drawCentredString(x_r + lado_r / 2, y_r - 0.32 * cm, 'REMITO')

    # Título, número y fecha (a la derecha)
    x_der = ANCHO - MARGEN

    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 20)
    c.drawRightString(x_der, y_banda + ALTO_ENCABEZADO - 1.35 * cm, 'REMITO')

    c.setFont('Helvetica', 9)
    c.setFillColor(colors.HexColor('#d9efe0'))
    c.drawRightString(x_der, y_banda + ALTO_ENCABEZADO - 2.05 * cm, 'N.º')

    c.setFont('Helvetica-Bold', 12)
    c.setFillColor(colors.white)
    c.drawRightString(
        x_der, y_banda + ALTO_ENCABEZADO - 2.6 * cm,
        _texto(remito.Numero_remito)
    )

    # Fecha en recuadro
    texto_fecha = f'Fecha  {_fecha(remito.Fecha_remito)}'
    c.setFont('Helvetica-Bold', 9)
    ancho_fecha = c.stringWidth(texto_fecha, 'Helvetica-Bold', 9) + 0.6 * cm
    c.setFillColor(AMARILLO)
    c.roundRect(
        x_der - ancho_fecha, y_banda + 0.45 * cm,
        ancho_fecha, 0.62 * cm, 4, stroke=0, fill=1
    )
    c.setFillColor(VERDE_OSCURO)
    c.drawRightString(x_der - 0.3 * cm, y_banda + 0.66 * cm, texto_fecha)

    # Pie de página
    c.setStrokeColor(BORDE)
    c.setLineWidth(0.6)
    c.line(MARGEN, 1.3 * cm, ANCHO - MARGEN, 1.3 * cm)

    c.setFillColor(SUAVE)
    c.setFont('Helvetica', 7)
    c.drawString(
        MARGEN, 0.85 * cm,
        'Copia del remito registrado en el Sistema de Gestión de Stock. '
        'Documento no válido como factura.'
    )
    c.drawRightString(
        ANCHO - MARGEN, 0.85 * cm,
        f'Emitido el {emitido}  ·  Página {doc.page}'
    )

    c.restoreState()


# ------------------------------------------------------------
# BLOQUES DEL CUERPO
# ------------------------------------------------------------

def _caja(titulo, filas, ancho):
    """Recuadro con título y pares etiqueta / valor en dos columnas."""

    contenido = [[_p(titulo, E_TITULO_CAJA), '']]

    for i in range(0, len(filas), 2):
        par = filas[i:i + 2]
        fila = []
        for etiqueta, valor in par:
            if valor == 'Anulado':
                fila.append([_p(etiqueta.upper(), E_ETIQUETA), _p(valor, E_VALOR_ROJO)])
                continue
            fila.append([
                _p(etiqueta.upper(), E_ETIQUETA),
                _p(valor, E_VALOR if len(str(valor)) <= 18 else E_VALOR_CHICO),
            ])
        if len(fila) == 1:
            fila.append('')
        contenido.append(fila)

    tabla = Table(contenido, colWidths=[ancho / 2, ancho / 2])
    tabla.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (-1, -1), VERDE_FILA),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDE),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, BORDE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    return tabla


def _tabla_lotes(lotes, ancho):
    """Detalle de la mercadería: un renglón por lote."""

    columnas = [
        ('Cajas', 1.4 * cm, E_CAB_TABLA),
        ('Producto', None, E_CAB_TABLA_I),
        ('N.º de lote', 2.9 * cm, E_CAB_TABLA),
        ('Vencimiento', 2.3 * cm, E_CAB_TABLA),
        ('Unid. x caja', 2.0 * cm, E_CAB_TABLA),
        ('Unidades', 2.0 * cm, E_CAB_TABLA),
    ]

    fijo = sum(c[1] for c in columnas if c[1])
    anchos = [c[1] or (ancho - fijo) for c in columnas]

    datos = [[_p(titulo, estilo) for titulo, _, estilo in columnas]]

    total_cajas = 0
    total_unidades = 0

    for lote in lotes:
        producto = lote.ID_Producto
        presentacion = _presentacion(producto)

        celda_producto = [_p(producto.Nombre_producto, E_CELDA)]
        if presentacion:
            celda_producto.append(_p(presentacion, E_CELDA_SUB))

        cajas = lote.Cantidad_cajas
        if cajas:
            total_cajas += cajas
        total_unidades += lote.Cantidad_ingresada or 0

        datos.append([
            _p(_numero(cajas) if cajas else '—', E_CELDA_C),
            celda_producto,
            _p(_texto(lote.Numero_lote), E_CELDA_C),
            _p(_fecha(lote.Fecha_vencimiento), E_CELDA_C),
            _p(_numero(lote.Unidades_por_caja) if lote.Unidades_por_caja else '—', E_CELDA_C),
            _p(_numero(lote.Cantidad_ingresada), E_CELDA_C),
        ])

    if not lotes:
        datos.append([_p('El remito no tiene lotes registrados.', E_CELDA), '', '', '', '', ''])

    # Fila de totales
    datos.append([
        _p(_numero(total_cajas) if total_cajas else '—', E_TOTAL_NUM),
        _p('', E_CELDA),
        '',
        '',
        _p('TOTAL', E_TOTAL),
        _p(_numero(total_unidades), E_TOTAL_NUM),
    ])

    ultima = len(datos) - 1

    estilo = [
        ('BACKGROUND', (0, 0), (-1, 0), VERDE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDE),
        ('LINEBELOW', (0, 1), (-1, ultima - 1), 0.5, colors.HexColor('#e4efe2')),
        ('BACKGROUND', (0, ultima), (-1, ultima), VERDE_CLARO),
        ('LINEABOVE', (0, ultima), (-1, ultima), 1, VERDE),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]

    # Filas alternadas
    for fila in range(1, ultima):
        if fila % 2 == 0:
            estilo.append(('BACKGROUND', (0, fila), (-1, fila), VERDE_FILA))

    if not lotes:
        estilo.append(('SPAN', (0, 1), (-1, 1)))

    tabla = Table(datos, colWidths=anchos, repeatRows=1)
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _bloque_firma(ancho):
    """Recibí conforme: firma, aclaración, DNI y fecha."""

    def linea(etiqueta):
        return [
            Spacer(1, 0.75 * cm),
            Table(
                [[_p(etiqueta, E_ETIQUETA)]],
                colWidths=[(ancho - 1.2 * cm) / 4 - 0.4 * cm],
                style=TableStyle([
                    ('LINEABOVE', (0, 0), (-1, 0), 0.8, SUAVE),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                ]),
            ),
        ]

    contenido = [
        [_p('RECIBÍ CONFORME LA MERCADERÍA DESCRIPTA EN ESTE REMITO', E_TITULO_CAJA), '', '', ''],
        [linea('FIRMA'), linea('ACLARACIÓN'), linea('DNI'), linea('FECHA')],
    ]

    tabla = Table(contenido, colWidths=[(ancho) / 4] * 4)
    tabla.setStyle(TableStyle([
        ('SPAN', (0, 0), (-1, 0)),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDE),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 10),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    return tabla


def _bloque_observaciones(remito, ancho):
    """Observaciones: si el remito está anulado, se muestran los datos de la anulación."""

    if remito.Estado_remito == 'Anulado':
        anulado_por = '—'
        if remito.ID_Usuario_anulacion:
            u = remito.ID_Usuario_anulacion
            anulado_por = f'{u.Nombre_usuario} {u.Apellido_usuario}'

        texto = (
            f'<b>REMITO ANULADO</b> el {_fecha(remito.Fecha_anulacion, "%d/%m/%Y %H:%M")} '
            f'por {_escapar(anulado_por)}.<br/>'
            f'Motivo: {_escapar(_texto(remito.Motivo_anulacion))}<br/>'
            'Las unidades de sus lotes fueron descontadas del stock.'
        )
        cuerpo = Paragraph(texto, E_ANULADO)
        fondo, borde = ROJO_CLARO, colors.HexColor('#f5c2c2')
    else:
        cuerpo = _p(
            'Cada lote registrado generó su movimiento de ingreso '
            'y actualizó el stock del producto.',
            E_TEXTO
        )
        fondo, borde = VERDE_FILA, BORDE

    tabla = Table(
        [[_p('OBSERVACIONES', E_TITULO_CAJA)], [cuerpo]],
        colWidths=[ancho],
    )
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), fondo),
        ('BOX', (0, 0), (-1, -1), 0.8, borde),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    return tabla


# ------------------------------------------------------------
# DOCUMENTO
# ------------------------------------------------------------

def generar_pdf_remito(remito, lotes, registrado_por=None, logo_path=None, emitido=''):
    """Devuelve los bytes del PDF del remito.

    remito          objeto Remitos (con ID_Proveedor cargado)
    lotes           lista de Lotes del remito (con ID_Producto cargado)
    registrado_por  texto con el usuario que registró el ingreso (opcional)
    logo_path       ruta del logo en disco (opcional)
    emitido         fecha y hora de emisión, ya formateada
    """

    buffer = BytesIO()

    doc = _DocumentoRemito(
        buffer,
        anulado=(remito.Estado_remito == 'Anulado'),
        pagesize=A4,
        leftMargin=MARGEN,
        rightMargin=MARGEN,
        topMargin=ALTO_ENCABEZADO + 0.8 * cm,
        bottomMargin=1.8 * cm,
        title=f'Remito {remito.Numero_remito}',
        author='Agroquímica del Valle',
    )

    ancho = ANCHO - 2 * MARGEN
    proveedor = remito.ID_Proveedor

    total_unidades = sum((l.Cantidad_ingresada or 0) for l in lotes)

    caja_proveedor = _caja('PROVEEDOR', [
        ('Razón social', _texto(proveedor.nombre_proveedor)),
        ('Teléfono', _texto(proveedor.telefono_proveedor)),
        ('Email', _texto(proveedor.email_proveedor)),
        ('Dirección', _texto(proveedor.direccion_proveedor)),
    ], ancho / 2 - 0.15 * cm)

    caja_remito = _caja('DATOS DEL REMITO', [
        ('Número', _texto(remito.Numero_remito)),
        ('Fecha', _fecha(remito.Fecha_remito)),
        ('Estado', _texto(remito.Estado_remito)),
        ('Lotes', _numero(len(lotes))),
        ('Unidades totales', _numero(total_unidades)),
        ('Registrado por', _texto(registrado_por)),
    ], ancho / 2 - 0.15 * cm)

    cajas = Table(
        [[caja_proveedor, caja_remito]],
        colWidths=[ancho / 2, ancho / 2],
    )
    cajas.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 0.15 * cm),
        ('LEFTPADDING', (1, 0), (1, 0), 0.15 * cm),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    destinatario = Table(
        [[
            _p('SEÑOR(ES)', E_ETIQUETA),
            _p('Agroquímica del Valle', E_VALOR),
        ]],
        colWidths=[2.4 * cm, ancho - 2.4 * cm],
    )
    destinatario.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 0.8, BORDE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))

    titulo_detalle = _p('DETALLE DE LA MERCADERÍA', E_TITULO_CAJA)

    elementos = [
        cajas,
        Spacer(1, 0.45 * cm),
        destinatario,
        Spacer(1, 0.5 * cm),
        titulo_detalle,
        Spacer(1, 0.2 * cm),
        _tabla_lotes(lotes, ancho),
        Spacer(1, 0.5 * cm),
        KeepTogether([
            _bloque_observaciones(remito, ancho),
            Spacer(1, 0.4 * cm),
            _bloque_firma(ancho),
        ]),
    ]

    def en_pagina(c, d):
        _dibujar_pagina(c, d, remito, logo_path, emitido)

    doc.build(elementos, onFirstPage=en_pagina, onLaterPages=en_pagina)

    pdf = buffer.getvalue()
    buffer.close()
    return pdf