from django.contrib import admin
from .models import (
    TiposProductos,
    Subtipos,
    Proveedores,
    TiposMovimientos,
    Perfiles,
    Permisos,
    PerfilesXPermisos,
    Usuarios,
    Productos,
    Lotes,
    Stock,
    Alertas,
    MovimientosStock
)


# Registramos los catálogos y tablas auxiliares
admin.site.register(TiposProductos)
admin.site.register(Subtipos)
admin.site.register(Proveedores)
admin.site.register(TiposMovimientos)
admin.site.register(Perfiles)
admin.site.register(Permisos)
admin.site.register(PerfilesXPermisos)


# Registramos las entidades principales
admin.site.register(Usuarios)
admin.site.register(Productos)
admin.site.register(Lotes)
admin.site.register(Stock)
admin.site.register(Alertas)
admin.site.register(MovimientosStock)