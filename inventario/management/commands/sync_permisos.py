from django.core.management.base import BaseCommand
from django.db import transaction

from inventario.models import Perfiles, PerfilesXPermisos, Permisos
from inventario.permissions import PERFILES_ADMIN, catalogo_plano


class Command(BaseCommand):
    help = 'Sincroniza la tabla PERMISOS con el catálogo definido en permissions.py'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limpiar',
            action='store_true',
            help='Elimina los permisos que ya no están en el catálogo '
                 'y no están asignados a ningún perfil.',
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        existentes = {
            p.Nombre_permiso.strip().lower(): p
            for p in Permisos.objects.all()
        }
        en_catalogo = set()
        creados = actualizados = 0

        for nombre, descripcion, _grupo in catalogo_plano():
            clave = nombre.lower()
            en_catalogo.add(clave)
            permiso = existentes.get(clave)

            if permiso is None:
                Permisos.objects.create(
                    Nombre_permiso=nombre,
                    Descripcion_permiso=descripcion,
                )
                creados += 1
                self.stdout.write(self.style.SUCCESS(f'  + creado: {nombre}'))
            elif (permiso.Nombre_permiso != nombre
                  or permiso.Descripcion_permiso != descripcion):
                permiso.Nombre_permiso = nombre
                permiso.Descripcion_permiso = descripcion
                permiso.save()
                actualizados += 1
                self.stdout.write(f'  ~ actualizado: {nombre}')
                
                # El perfil Administrador tiene todos los permisos del catálogo.
        todos = {
            p.Nombre_permiso.strip().lower(): p
            for p in Permisos.objects.all()
        }
        asignados_admin = 0

        for perfil in Perfiles.objects.filter(Nombre_perfil__in=PERFILES_ADMIN):
            for nombre, _descripcion, _grupo in catalogo_plano():
                permiso = todos.get(nombre.lower())

                if permiso:
                    _, nuevo = PerfilesXPermisos.objects.get_or_create(
                        ID_Perfil=perfil,
                        ID_Permiso=permiso,
                    )
                    asignados_admin += int(nuevo)

        if asignados_admin:
            self.stdout.write(self.style.SUCCESS(
                f'  + {asignados_admin} permisos asignados al Administrador'
            ))

        huerfanos = [p for k, p in existentes.items() if k not in en_catalogo]

        for p in huerfanos:
            asignado_a = list(p.perfiles.values_list('Nombre_perfil', flat=True))

            if opciones['limpiar'] and not asignado_a:
                p.delete()
                self.stdout.write(self.style.WARNING(f'  - eliminado: {p.Nombre_permiso}'))
            else:
                detalle = f' (asignado a: {", ".join(asignado_a)})' if asignado_a else ''
                self.stdout.write(self.style.WARNING(
                    f'  ? sin función en el sistema: {p.Nombre_permiso}{detalle}'
                ))

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {creados} creados, {actualizados} actualizados, '
            f'{len(huerfanos)} fuera del catálogo.'
        ))