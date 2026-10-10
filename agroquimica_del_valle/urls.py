from django.urls import path
from inventario import views

urlpatterns = [
    # Login
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('cerrar-sesion/', views.cerrar_sesion, name='cerrar_sesion'),

    # Panel principal
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
    path('tipos-productos/baja/<int:pk>/', views.dar_baja_tipo_producto, name='dar_baja_tipo_producto'),

    # Subtipos
    path('subtipos/', views.gestion_subtipos, name='gestion_subtipos'),
    path('subtipos/crear/', views.crear_subtipo, name='crear_subtipo'),
    path('subtipos/editar/<int:pk>/', views.editar_subtipo, name='editar_subtipo'),
    path('subtipos/cambiar-estado/<int:pk>/', views.cambiar_estado_subtipo, name='cambiar_estado_subtipo'),


    # Usuarios
    path('usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
    path('usuarios/crear/', views.crear_usuario, name='crear_usuario'),
    path('usuarios/editar/<int:pk>/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/baja/<int:pk>/', views.dar_baja_usuario, name='dar_baja_usuario'),
    path('usuarios/restablecer/<int:pk>/', views.restablecer_contrasena, name='restablecer_contrasena'),
    path('usuarios/cambiar-contrasena/', views.cambiar_contrasena, name='cambiar_contrasena'),
    path('usuarios/activar/<int:id>/', views.activar_usuario, name='activar_usuario'),

    # Perfiles
    path('perfiles/', views.gestion_perfiles, name='gestion_perfiles'),
    path('perfiles/crear/', views.crear_perfil, name='crear_perfil'),
    path('perfiles/editar/<int:pk>/', views.editar_perfil, name='editar_perfil'),
    path('perfiles/cambiar-estado/<int:id>/', views.cambiar_estado_perfil, name='cambiar_estado_perfil'),
    path('mis-permisos/', views.mis_permisos, name='mis_permisos'),


    # Productos
    path('productos/', views.gestion_productos, name='gestion_productos'),
    path('productos/crear/', views.crear_producto, name='crear_producto'),
    path('productos/editar/<int:pk>/', views.editar_producto, name='editar_producto'),
    path('productos/cambiar-estado/<int:pk>/', views.cambiar_estado_producto, name='cambiar_estado_producto'),


    # ============================================================
    # GESTIÓN DE LOTES
    # ============================================================

    path('ingreso-lote/', views.registrar_ingreso_lote, name='registrar_ingreso_lote'),
    path('ingreso-lote/editar/<int:id>/', views.editar_lote, name='editar_lote'),
    path('ingreso-lote/cambiar-estado/<int:id>/', views.cambiar_estado_lote, name='cambiar_estado_lote'),

    # Movimientos de stock
    path('movimientos-stock/', views.gestion_movimientos_stock, name='gestion_movimientos_stock'),
    path('movimientos-stock/crear/', views.crear_movimiento_stock, name='crear_movimiento_stock'),

    # Alertas
    path('historial-alertas/', views.gestion_alertas, name='historial_alertas'),
    path('alertas/atender/<int:id_alerta>/', views.atender_alerta, name='atender_alerta'),

    # Permisos
    path('permisos/', views.gestion_permisos, name='gestion_permisos'),
    path('permisos/crear/', views.crear_permiso, name='crear_permiso'),
    path('permisos/editar/<int:pk>/', views.editar_permiso, name='editar_permiso'),
    path('permisos/eliminar/<int:pk>/', views.eliminar_permiso, name='eliminar_permiso'),
    
]