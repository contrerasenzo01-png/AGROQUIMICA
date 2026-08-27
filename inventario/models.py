from django.db import models

class TiposProductos(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Tipos de Productos" # <-- Nombre correcto en el Admin

    def __str__(self):
        return self.nombre


class GruposQuimicos(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Grupos Químicos"

    def __str__(self):
        return self.nombre


class Proveedores(models.Model):
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
        db_table = 'proveedores'
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
    puesto = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Tipos de Empleados"

    def __str__(self):
        return self.puesto


class TiposMovimientos(models.Model):
    descripcion = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Tipos de Movimientos"

    def __str__(self):
        return self.descripcion


class Empleados(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    tipo_empleado = models.ForeignKey(TiposEmpleados, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "Empleados"

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class Productos(models.Model):
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)
    tipo_producto = models.ForeignKey(TiposProductos, on_delete=models.CASCADE)
    grupos_quimicos = models.ManyToManyField(GruposQuimicos, through='ProductosXGruposQuimicos')
    proveedores = models.ManyToManyField(Proveedores, through='ProductosXProveedores')

    class Meta:
        verbose_name_plural = "Productos"

    def __str__(self):
        return self.nombre


class ProductosXGruposQuimicos(models.Model):
    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    grupo_quimico = models.ForeignKey(GruposQuimicos, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "Productos por Grupos Químicos"


class ProductosXProveedores(models.Model):
    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    proveedor = models.ForeignKey(Proveedores, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "Productos por Proveedores"


class Stock(models.Model):
    producto = models.OneToOneField(Productos, on_delete=models.CASCADE)
    cantidad = models.IntegerField(default=0)

    class Meta:
        verbose_name_plural = "Stock"

    def __str__(self):
        return f"{self.producto.nombre} - Cantidad: {self.cantidad}"


class Alertas(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    mensaje = models.CharField(max_length=255)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Alertas"


class MovimientosStock(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    empleado = models.ForeignKey(Empleados, on_delete=models.CASCADE)
    tipo_movimiento = models.ForeignKey(TiposMovimientos, on_delete=models.CASCADE)
    cantidad = models.IntegerField()
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Movimientos de Stock"