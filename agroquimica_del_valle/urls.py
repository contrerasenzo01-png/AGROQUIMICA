from django.urls import path
from inventario import views

urlpatterns = [
    #Login
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),

    #Panel principal
    path('panel-principal/', views.panel_principal, name='panel_principal'),

    # Proveedores
    path('proveedores/', views.gestion_proveedores, name='gestion_proveedores'),
    path('proveedores/crear/', views.crear_proveedor, name='crear_proveedor'),
    path('proveedores/editar/<int:pk>/', views.editar_proveedor, name='editar_proveedor'),
    path('proveedores/estado/<int:pk>/', views.cambiar_estado_proveedor, name='cambiar_estado_proveedor'),

    # Tipos de productos
    path('tipos-productos/', views.gestion_tipos_productos, name='gestion_tipos_productos'),
    path('tipos-productos/crear/', views.crear_tipo_producto, name='crear_tipo_producto'),
    path('tipos-productos/editar/<int:pk>/', views.editar_tipo_producto, name='editar_tipo_producto'),

    # Agroquímicos
    path('agroquimicos/', views.gestion_agroquimicos, name='gestion_agroquimicos'),
    path('agroquimicos/crear/', views.crear_agroquimico, name='crear_agroquimico'),
    path('agroquimicos/editar/<int:pk>/', views.editar_agroquimico, name='editar_agroquimico'),

    # Usuarios
    path('usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
    path('usuarios/crear/', views.crear_usuario, name='crear_usuario'),
    path('usuarios/editar/<int:pk>/', views.editar_usuario, name='editar_usuario'),

    # Tipos de movimientos
    path('tipos-movimientos/', views.gestion_tipos_movimientos, name='gestion_tipos_movimientos'),
    path('tipos-movimientos/crear/', views.crear_tipo_movimiento, name='crear_tipo_movimiento'),
    path('tipos-movimientos/editar/<int:pk>/', views.editar_tipo_movimiento, name='editar_tipo_movimiento'),

    # Productos
    path('productos/', views.gestion_productos, name='gestion_productos'),
    path('productos/crear/', views.crear_producto, name='crear_producto'),
    path('productos/editar/<int:pk>/', views.editar_producto, name='editar_producto'),

    # Productos por proveedor
    path('productos-proveedores/', views.gestion_productos_proveedores, name='gestion_productos_proveedores'),

    # Stock
    path('stock/', views.gestion_stock, name='gestion_stock'),
    path('stock/crear/', views.crear_stock, name='crear_stock'),
    path('stock/editar/<int:pk>/', views.editar_stock, name='editar_stock'),

    # Movimientos de stock
    path('movimientos-stock/', views.gestion_movimientos_stock, name='gestion_movimientos_stock'),
    path('movimientos-stock/crear/', views.crear_movimiento_stock, name='crear_movimiento_stock'),

    # Alertas
    path('alertas/', views.gestion_alertas, name='gestion_alertas'),
]