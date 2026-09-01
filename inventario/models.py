from django.db import models

class TiposProductos(models.Model):
    ID_Tipo_producto = models.AutoField(primary_key=True)
    Nombre_tipo_producto = models.CharField(max_length=50)

    class Meta:
        db_table = 'TIPOS_PRODUCTOS'
        verbose_name_plural = "Tipos de Productos"

    def __str__(self):
        return self.Nombre_tipo_producto


class Agroquimicos(models.Model):
    ID_Agroquimico = models.AutoField(primary_key=True)
    Nombre_agroquimico = models.CharField(max_length=60)
    Descripcion_agroquimico = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        db_table = 'AGROQUIMICOS'
        verbose_name_plural = "Agroquímicos"

    def __str__(self):
        return self.Nombre_agroquimico


class Proveedores(models.Model):
    # Agrega esta línea al inicio del modelo:
    ID_Proveedor = models.AutoField(primary_key=True, db_column='ID_Proveedor')

    ESTADO_CHOICES = [
        (True, 'Activo'),
        (False, 'Inactivo'),
    ]

    nombre_proveedor = models.CharField(max_length=150, unique=True, verbose_name="Nombre del Proveedor")
    telefono_proveedor = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono")
    email_proveedor = models.EmailField(blank=True, null=True, verbose_name="Email")
    direccion_proveedor = models.CharField(max_length=255, blank=True, null=True, verbose_name="Dirección")
    estado_proveedor = models.BooleanField(default=True, choices=ESTADO_CHOICES, verbose_name="Estado")

    class Meta:
        db_table = 'PROVEEDORES'
        verbose_name_plural = "Proveedores"

    def __str__(self):
        return self.nombre_proveedor

    @property
    def iniciales(self):
        palabras = self.nombre_proveedor.split()
        if len(palabras) >= 2:
            return f"{palabras[0][0]}{palabras[1][0]}".upper()
        return self.nombre_proveedor[:2].upper()


class TiposEmpleados(models.Model):
    ID_Tipo_empleado = models.AutoField(primary_key=True)
    Nombre_tipo_empleado = models.CharField(max_length=50)

    class Meta:
        db_table = 'TIPOS_EMPLEADOS'
        verbose_name_plural = "Tipos de Empleados"

    def __str__(self):
        return self.Nombre_tipo_empleado


class TiposMovimientos(models.Model):
    ID_Tipo_movimiento = models.AutoField(primary_key=True)
    Nombre_tipo_movimiento = models.CharField(max_length=50)

    class Meta:
        db_table = 'TIPOS_MOVIMIENTOS'
        verbose_name_plural = "Tipos de Movimientos"

    def __str__(self):
        return self.Nombre_tipo_movimiento


class Empleados(models.Model):
    ID_Empleado = models.AutoField(primary_key=True)
    Nombre_empleado = models.CharField(max_length=50)
    Apellido_empleado = models.CharField(max_length=50)
    Telefono_empleado = models.CharField(max_length=20, blank=True, null=True)
    Email_empleado = models.EmailField(max_length=100, blank=True, null=True)
    ID_Tipo_empleado = models.ForeignKey(TiposEmpleados, on_delete=models.CASCADE, db_column='ID_Tipo_empleado')

    class Meta:
        db_table = 'EMPLEADOS'
        verbose_name_plural = "Empleados"

    def __str__(self):
        return f"{self.Nombre_empleado} {self.Apellido_empleado}"


class Productos(models.Model):
    ID_Producto = models.AutoField(primary_key=True)
    ID_Tipo_producto = models.ForeignKey(TiposProductos, on_delete=models.CASCADE, db_column='ID_Tipo_producto')
    Nombre_producto = models.CharField(max_length=50)
    Descripcion_producto = models.CharField(max_length=100, blank=True, null=True)
    Fecha_vencimiento = models.DateField(blank=True, null=True)
    Precio = models.DecimalField(max_digits=10, decimal_places=2)
    agroquimicos = models.ManyToManyField(Agroquimicos, through='ProductosXAgroquimicos')
    proveedores = models.ManyToManyField(Proveedores, through='ProductosXProveedores')

    class Meta:
        db_table = 'PRODUCTOS'
        verbose_name_plural = "Productos"

    def __str__(self):
        return self.Nombre_producto


class ProductosXAgroquimicos(models.Model):
    ID_Producto = models.ForeignKey(Productos, on_delete=models.CASCADE, db_column='ID_Producto')
    ID_Agroquimico = models.ForeignKey(Agroquimicos, on_delete=models.CASCADE, db_column='ID_Agroquimico')

    class Meta:
        db_table = 'PRODUCTOS_X_AGROQUIMICOS'
        unique_together = (('ID_Producto', 'ID_Agroquimico'),)
        verbose_name_plural = "Productos por Agroquímicos"


class ProductosXProveedores(models.Model):
    ID_Producto = models.ForeignKey(Productos, on_delete=models.CASCADE, db_column='ID_Producto')
    ID_Proveedor = models.ForeignKey(Proveedores, on_delete=models.CASCADE, db_column='ID_Proveedor')

    class Meta:
        db_table = 'PRODUCTOS_X_PROVEEDORES'
        unique_together = (('ID_Producto', 'ID_Proveedor'),)
        verbose_name_plural = "Productos por Proveedores"


class Stock(models.Model):
    ID_Stock = models.AutoField(primary_key=True)
    ID_Producto = models.OneToOneField(Productos, on_delete=models.CASCADE, db_column='ID_Producto')    
    Cantidad_stock = models.IntegerField()
    Stock_minimo = models.IntegerField()

    class Meta:
        db_table = 'STOCK'
        verbose_name_plural = "Stock"

    def __str__(self):
        return f"{self.ID_Producto.Nombre_producto} - Stock: {self.Cantidad_stock}"


class Alertas(models.Model):
    ID_Alerta = models.AutoField(primary_key=True)
    ID_Stock = models.ForeignKey(Stock, on_delete=models.CASCADE, db_column='ID_Stock')
    Mensaje = models.CharField(max_length=255)
    Fecha_hora_alerta = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ALERTAS'
        verbose_name_plural = "Alertas"


class MovimientosStock(models.Model):
    ID_Movimiento_stock = models.AutoField(primary_key=True)
    ID_Empleado = models.ForeignKey(Empleados, on_delete=models.CASCADE, db_column='ID_Empleado')
    ID_Tipo_movimiento = models.ForeignKey(TiposMovimientos, on_delete=models.CASCADE, db_column='ID_Tipo_movimiento')
    ID_Stock = models.ForeignKey(Stock, on_delete=models.CASCADE, db_column='ID_Stock')
    Fecha_hora_movimiento = models.DateTimeField(auto_now_add=True)
    Cantidad = models.IntegerField()

    class Meta:
        db_table = 'MOVIMIENTOS_STOCK'
        verbose_name_plural = "Movimientos de Stock"