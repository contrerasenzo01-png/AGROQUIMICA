
"""
Baja de lotes vencidos · Agroquímica del Valle

Registra la salida por vencimiento de un lote vencido
que todavía tiene stock.

Al confirmar:
  - Se crea un movimiento de salida por vencimiento.
  - El lote queda en cero.
  - Se descuenta la cantidad del stock del producto.
  - La alerta de vencimiento del lote se marca como atendida.
  - Se revisa el stock mínimo.
  - Se registra la operación en Auditoría como EGRESO_VENCIMIENTO.

Permiso: Registrar egresos de stock.
"""

from django.contrib import messages
from django.db import DatabaseError, transaction
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .alertas import TIPO_VENCIMIENTO, revisar_stock
from .auditoria import registrar_auditoria, snapshot
from .models import (
    Alertas,
    Lotes,
    MovimientosStock,
    Stock,
    TiposMovimientos,
)
from .permissions import usuario_con_acceso


TIPO_SALIDA_VENCIMIENTO = 'Salida por vencimiento de producto'


@require_POST
def baja_lote_vencido(request, id_lote):
    """Da de baja por vencimiento todo el stock que le queda a un lote."""

    usuario = usuario_con_acceso(
        request,
        'egresos',
        gestionar=True
    )

    if not usuario:
        messages.error(
            request,
            'No tenés permiso para dar de baja lotes vencidos.'
        )
        return redirect('panel_principal')

    observacion = request.POST.get(
        'observacion',
        ''
    ).strip()[:200]

    lote_base = Lotes.objects.filter(
        ID_Lote=id_lote
    ).first()

    if not lote_base:
        messages.error(
            request,
            'El lote seleccionado no existe.'
        )
        return redirect('registrar_ingreso_lote')

    tipo_salida, _ = TiposMovimientos.objects.get_or_create(
        Nombre_tipo_movimiento=TIPO_SALIDA_VENCIMIENTO
    )

    hoy = timezone.localdate()

    try:
        with transaction.atomic():

            # Bloqueo del stock y del lote para evitar
            # modificaciones simultáneas.

            stock = Stock.objects.select_for_update().filter(
                ID_Producto_id=lote_base.ID_Producto_id
            ).first()

            lote = Lotes.objects.select_for_update().select_related(
                'ID_Producto'
            ).get(
                ID_Lote=id_lote
            )

            producto = lote.ID_Producto
            cantidad = lote.Cantidad_actual

            # Verificar vencimiento.

            if (
                not lote.Fecha_vencimiento
                or lote.Fecha_vencimiento >= hoy
            ):
                messages.error(
                    request,
                    f'El lote {lote.Numero_lote} todavía no está vencido.'
                )
                return redirect('registrar_ingreso_lote')

            # Verificar existencia de stock en el lote.

            if cantidad <= 0:
                messages.error(
                    request,
                    f'El lote {lote.Numero_lote} no tiene stock para dar de baja.'
                )
                return redirect('registrar_ingreso_lote')

            if not stock:
                messages.error(
                    request,
                    'El producto no tiene stock registrado.'
                )
                return redirect('registrar_ingreso_lote')

            if cantidad > stock.Cantidad_stock:
                messages.error(
                    request,
                    'La cantidad del lote supera el stock del producto. '
                    'Revisá el stock antes de dar de baja.'
                )
                return redirect('registrar_ingreso_lote')

            # Guardar cantidades anteriores.

            lote_antes = cantidad
            stock_antes = stock.Cantidad_stock

            # Actualizar lote.

            lote.Cantidad_actual = 0

            lote.save(
                update_fields=['Cantidad_actual']
            )

            # Descontar stock del producto.

            stock.Cantidad_stock -= cantidad

            stock.save(
                update_fields=['Cantidad_stock']
            )

            # Preparar observaciones.

            detalle = (
                f'Baja por vencimiento del lote {lote.Numero_lote}'
                f' (venció el {lote.Fecha_vencimiento:%d/%m/%Y})'
            )

            if observacion:
                detalle = f'{detalle}. {observacion}'

            # Registrar movimiento de stock.

            movimiento = MovimientosStock.objects.create(
                ID_Usuario=usuario,
                ID_Tipo_movimiento=tipo_salida,
                ID_Lote=lote,
                Cantidad_movimiento_stock=cantidad,
                Observaciones=detalle[:255]
            )

            # Registrar auditoría como EGRESO_VENCIMIENTO.

            registrar_auditoria(
                usuario,
                'Movimientos de Stock',
                movimiento,
                'EGRESO_VENCIMIENTO',
                {},
                {
                    'Tipo_movimiento': TIPO_SALIDA_VENCIMIENTO,
                    'ID_Producto': producto.pk,
                    'Producto': producto.Nombre_producto,
                    'Lote': lote.Numero_lote,
                    'Fecha_vencimiento': (
                        lote.Fecha_vencimiento.strftime('%d/%m/%Y')
                    ),
                    'Cantidad': cantidad,
                    'Lote_antes': lote_antes,
                    'Lote_despues': 0,
                    'Stock_antes': stock_antes,
                    'Stock_despues': stock.Cantidad_stock,
                    'Observaciones': detalle[:255],
                }
            )

            # Marcar como atendidas las alertas
            # correspondientes al lote vencido.

            pendientes = Alertas.objects.filter(
                ID_Stock=stock,
                Tipo_alerta=TIPO_VENCIMIENTO,
                Atendida=False,
                Mensaje__contains=f'[LOTE_ID:{lote.ID_Lote}]',
            )

            for alerta in pendientes:

                alerta_antes = snapshot(alerta)

                alerta.Atendida = True
                alerta.ID_Usuario = usuario
                alerta.Fecha_hora_atencion = timezone.now()

                alerta.save(
                    update_fields=[
                        'Atendida',
                        'ID_Usuario',
                        'Fecha_hora_atencion',
                    ]
                )

                registrar_auditoria(
                    usuario,
                    'Historial de alertas',
                    alerta,
                    'ATENCION_ALERTA',
                    alerta_antes,
                    snapshot(alerta)
                )

            # Revisar stock mínimo y generar alerta
            # si corresponde.

            stock_bajo = revisar_stock(
                stock,
                usuario
            )

    except Lotes.DoesNotExist:

        messages.error(
            request,
            'El lote seleccionado no existe.'
        )

        return redirect('registrar_ingreso_lote')

    except DatabaseError:

        messages.error(
            request,
            'Ocurrió un error en la base de datos. '
            'No se registró la baja por vencimiento.'
        )

        return redirect('registrar_ingreso_lote')

    # Mensaje de confirmación.

    messages.success(
        request,
        f'Baja por vencimiento registrada: {cantidad} unidad(es) de '
        f'"{producto.Nombre_producto}" (lote {lote.Numero_lote}). '
        f'Stock actual: {stock.Cantidad_stock}.'
    )

    if stock_bajo:

        messages.warning(
            request,
            f'Atención: "{producto.Nombre_producto}" está en o por '
            f'debajo del stock mínimo ({stock.Stock_minimo}).'
        )

    return redirect('registrar_ingreso_lote')
