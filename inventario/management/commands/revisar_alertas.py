"""
Job programado de alertas · Agroquímica del Valle

Evalúa las reglas que dependen del paso del tiempo y deja las
notificaciones que correspondan:

  - Vencimientos: lotes que vencen dentro de "dias_aviso_vencimiento".
  - Stock mínimo: productos que están en su umbral o por debajo
    (por si el umbral cambió desde la configuración).

Se programa para que corra al menos una vez por día, por ejemplo con el
Programador de tareas de Windows:

    schtasks /create /sc daily /st 08:00 /tn "Agroquimica - alertas" ^
        /tr "D:\\AGROQUIMICA\\revisar_alertas.bat"

No genera duplicados: si una alerta o notificación ya existe para el
mismo evento, no se vuelve a crear (ver notificaciones.py).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from inventario.alertas import revisar_stock, revisar_vencimientos
from inventario.models import Notificacion, Stock
from inventario.notificaciones import asegurar_configuracion


class Command(BaseCommand):
    help = 'Evalúa las reglas de alertas (vencimientos y stock mínimo) y genera las notificaciones.'

    def handle(self, *args, **opciones):
        asegurar_configuracion()
        antes = Notificacion.objects.count()

        with transaction.atomic():
            lotes = revisar_vencimientos()

            en_minimo = 0
            for stock in Stock.objects.select_related('ID_Producto').filter(
                ID_Producto__Estado_producto='Activo'
            ):
                en_minimo += int(revisar_stock(stock))

        nuevas = Notificacion.objects.count() - antes

        self.stdout.write(self.style.SUCCESS(
            f'Revisión terminada: {len(lotes)} lote(s) por vencer o vencidos, '
            f'{en_minimo} producto(s) en stock mínimo, '
            f'{nuevas} notificación(es) nueva(s).'
        ))
