from django.db import models

class TiposProductos(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Tipos de Productos" # <-- Nombre correcto en el Admin

    def _str_(self):
        return self.nombre


class GruposQuimicos(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Grupos Químicos"

    def _str_(self):
        return self.nombre


class Proveedores(models.Model):
    razon_social = models.CharField(max_length=150)
    cuit = models.CharField(max_length=20, blank=True, null=True)
    telefono = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Proveedores"

    def _str_(self):
        return self.razon_social


class TiposEmpleados(models.Model):
    puesto = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Tipos de Empleados"

    def _str_(self):
        return self.puesto


class TiposMovimientos(models.Model):
    descripcion = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Tipos de Movimientos"

    def _str_(self):
        return self.descripcion


class Empleados(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    tipo_empleado = models.ForeignKey(TiposEmpleados, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "Empleados"

    def _str_(self):
        return f"{self.nombre} {self.apellido}"


class Productos(models.Model):
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)
    tipo_producto = models.ForeignKey(TiposProductos, on_delete=models.CASCADE)
    grupos_quimicos = models.ManyToManyField(GruposQuimicos, through='ProductosXGruposQuimicos')
    proveedores = models.ManyToManyField(Proveedores, through='ProductosXProveedores')

    class Meta:
        verbose_name_plural = "Productos"

    def _str_(self):
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

    def _str_(self):
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