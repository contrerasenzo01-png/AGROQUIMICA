from django.contrib import admin
from .models import (
    TiposProductos, GruposQuimicos, Proveedores, TiposEmpleados,
    TiposMovimientos, Empleados, Productos,
    ProductosXGruposQuimicos, ProductosXProveedores,
    Stock, Alertas, MovimientosStock
)

# Registramos los catálogos/tablas auxiliares
admin.site.register(TiposProductos)
admin.site.register(GruposQuimicos)
admin.site.register(Proveedores)
admin.site.register(TiposEmpleados)
admin.site.register(TiposMovimientos)

# Registramos las entidades principales
admin.site.register(Empleados)
admin.site.register(Productos)
admin.site.register(ProductosXGruposQuimicos)
admin.site.register(ProductosXProveedores)
admin.site.register(Stock)
admin.site.register(Alertas)
admin.site.register(MovimientosStock)