"""
Carga en la auditoría las altas que ya existían antes de que se registraran,
y ordena las que ya se habían cargado.

Cómo se ejecuta (desde la carpeta donde está manage.py):

    python manage.py shell -c "exec(open('cargar_auditoria_previa.py', encoding='utf-8').read())"

Se puede ejecutar más de una vez: no duplica lo que ya está registrado.

Qué carga:
  - Remitos: con el usuario y la fecha REALES, tomados del movimiento de
    entrada de sus lotes.
  - Productos y proveedores: el sistema no guardó quién ni cuándo los creó.
    Se atribuyen al usuario indicado abajo y cada registro lleva una nota
    que lo aclara.

Fecha de las altas cargadas a posteriori:
  Como la fecha real no existe, se coloca UN MINUTO ANTES de la primera
  actividad registrada de ese mismo registro (su primera modificación o el
  primer movimiento de stock de sus lotes). Así la creación siempre queda
  antes que sus modificaciones. Si el registro no tiene ninguna actividad,
  conserva la fecha de la carga.
"""

from datetime import timedelta

from django.db.models import Min

from inventario.auditoria import snapshot
from inventario.models import (
    LogAuditoria,
    MovimientosStock,
    Productos,
    Proveedores,
    Remitos,
    Stock,
    Usuarios,
)

# Usuario al que se atribuyen las altas sin autor registrado.
USUARIO_AUTOR = 'perezm'

NOTA = (
    'Alta anterior a la auditoría, cargada a posteriori. '
    'La fecha es aproximada: se ubica antes de la primera actividad '
    'registrada, y no es el momento real de la creación.'
)

MODELOS = {
    'Productos': Productos,
    'Proveedores': Proveedores,
    'Remitos': Remitos,
}

try:
    autor = Usuarios.objects.select_related('ID_Perfil').get(
        Usuario=USUARIO_AUTOR
    )
except Usuarios.DoesNotExist:
    raise SystemExit(
        'No existe el usuario "%s". Cambiá USUARIO_AUTOR al principio '
        'del archivo.' % USUARIO_AUTOR
    )


def ya_registrado(entidad, pk):
    return LogAuditoria.objects.filter(
        Seccion=entidad,
        ID_Registro=pk,
        Accion='CREACION'
    ).exists()


def fecha_previa(entidad, objeto):
    """Un minuto antes de la primera actividad conocida del registro."""

    fechas = []

    primera_auditoria = LogAuditoria.objects.filter(
        Seccion=entidad,
        ID_Registro=objeto.pk
    ).exclude(
        Accion='CREACION'
    ).aggregate(m=Min('Fecha_hora'))['m']

    if primera_auditoria:
        fechas.append(primera_auditoria)

    movimientos = None

    if entidad == 'Productos':
        movimientos = MovimientosStock.objects.filter(
            ID_Lote__ID_Producto=objeto
        )
    elif entidad == 'Proveedores':
        movimientos = MovimientosStock.objects.filter(
            ID_Lote__ID_Remito__ID_Proveedor=objeto
        )
    elif entidad == 'Remitos':
        movimientos = MovimientosStock.objects.filter(
            ID_Lote__ID_Remito=objeto
        )

    if movimientos is not None:
        primer_movimiento = movimientos.aggregate(
            m=Min('Fecha_hora_movimiento')
        )['m']

        if primer_movimiento:
            fechas.append(primer_movimiento)

    if not fechas:
        return None

    return min(fechas) - timedelta(minutes=1)


def registrar(usuario, entidad, objeto, despues, fecha=None, con_nota=True):
    if con_nota:
        despues = dict(despues, Nota=NOTA)

    log = LogAuditoria.objects.create(
        ID_Usuario=usuario,
        Seccion=entidad,
        ID_Registro=objeto.pk,
        Accion='CREACION',
        Valores_anteriores={},
        Valores_actuales=despues,
    )

    # La fecha se completa sola al crear; si se conoce una mejor, se corrige.
    if fecha is None and con_nota:
        fecha = fecha_previa(entidad, objeto)

    if fecha is not None:
        LogAuditoria.objects.filter(pk=log.pk).update(Fecha_hora=fecha)


cargados = {'Productos': 0, 'Proveedores': 0, 'Remitos': 0}

# ---------------- PRODUCTOS ----------------
for producto in Productos.objects.all():
    if ya_registrado('Productos', producto.pk):
        continue

    despues = snapshot(producto)

    stock = Stock.objects.filter(ID_Producto=producto).first()
    if stock:
        despues['Stock_minimo'] = stock.Stock_minimo

    registrar(autor, 'Productos', producto, despues)
    cargados['Productos'] += 1

# ---------------- PROVEEDORES ----------------
for proveedor in Proveedores.objects.all():
    if ya_registrado('Proveedores', proveedor.pk):
        continue

    registrar(autor, 'Proveedores', proveedor, snapshot(proveedor))
    cargados['Proveedores'] += 1

# ---------------- REMITOS (usuario y fecha reales) ----------------
for remito in Remitos.objects.all():
    if ya_registrado('Remitos', remito.pk):
        continue

    entrada = MovimientosStock.objects.select_related(
        'ID_Usuario__ID_Perfil'
    ).filter(
        ID_Lote__ID_Remito=remito,
        ID_Tipo_movimiento__Nombre_tipo_movimiento__iexact='Entrada de lote'
    ).order_by('Fecha_hora_movimiento').first()

    if entrada:
        registrar(
            entrada.ID_Usuario,
            'Remitos',
            remito,
            snapshot(remito),
            fecha=entrada.Fecha_hora_movimiento,
            con_nota=False
        )
    else:
        registrar(autor, 'Remitos', remito, snapshot(remito))

    cargados['Remitos'] += 1

# ---------------- ORDENAR LAS YA CARGADAS ----------------
# Las altas cargadas en una ejecución anterior tenían la fecha de la carga.
# Se las mueve antes de la primera actividad de su registro.
reubicadas = 0

for log in LogAuditoria.objects.filter(
    Accion='CREACION',
    Valores_actuales__has_key='Nota'
):
    modelo = MODELOS.get(log.Seccion)

    if modelo is None:
        continue

    objeto = modelo.objects.filter(pk=log.ID_Registro).first()

    if objeto is None:
        continue

    fecha = fecha_previa(log.Seccion, objeto)

    if fecha is not None and fecha < log.Fecha_hora:
        # La nota se actualiza: ya no es la fecha de la carga, sino aproximada.
        actuales = dict(log.Valores_actuales, Nota=NOTA)

        LogAuditoria.objects.filter(pk=log.pk).update(
            Fecha_hora=fecha,
            Valores_actuales=actuales
        )
        reubicadas += 1

print('Altas cargadas en la auditoría:', cargados)
print('Altas anteriores reubicadas antes de su primera actividad:', reubicadas)