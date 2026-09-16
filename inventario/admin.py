from django.contrib import admin
from .models import (
    TiposProductos, Agroquimicos, Proveedores,
    TiposMovimientos, Usuarios, Productos,
    ProductosXAgroquimicos, ProductosXProveedores,
    Stock, Alertas, MovimientosStock
)

# Registramos los catálogos/tablas auxiliares
admin.site.register(TiposProductos)
admin.site.register(Agroquimicos)
admin.site.register(Proveedores)
admin.site.register(TiposMovimientos)

# Registramos las entidades principales
admin.site.register(Usuarios)
admin.site.register(Productos)
admin.site.register(ProductosXAgroquimicos)
admin.site.register(ProductosXProveedores)
admin.site.register(Stock)
admin.site.register(Alertas)
admin.site.register(MovimientosStock)