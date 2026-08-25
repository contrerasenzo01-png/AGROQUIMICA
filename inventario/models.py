from django.db import models

# --- TABLAS DE CATÁLOGOS / TIPOS ---

class TiposProductos(models.Model):
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre


class GruposQuimicos(models.Model):
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre


class Proveedores(models.Model):
    razon_social = models.CharField(max_length=150)
    cuit = models.CharField(max_length=20, blank=True, null=True)
    telefono = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return self.razon_social


class TiposEmpleados(models.Model):
    puesto = models.CharField(max_length=100)

    def __str__(self):
        return self.puesto


class TiposMovimientos(models.Model):
    descripcion = models.CharField(max_length=100) # Ej: Entrada, Salida, Ajuste

    def __str__(self):
        return self.descripcion


# --- ENTIDADES PRINCIPALES Y RELACIONADAS ---

class Empleados(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    tipo_empleado = models.ForeignKey(TiposEmpleados, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class Productos(models.Model):
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)
    tipo_producto = models.ForeignKey(TiposProductos, on_delete=models.CASCADE)
    grupos_quimicos = models.ManyToManyField(GruposQuimicos, through='ProductosXGruposQuimicos')
    proveedores = models.ManyToManyField(Proveedores, through='ProductosXProveedores')

    def __str__(self):
        return self.nombre


# --- TABLAS INTERMEDIAS (MUCHOS A MUCHOS) ---

class ProductosXGruposQuimicos(models.Model):
    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    grupo_quimico = models.ForeignKey(GruposQuimicos, on_delete=models.CASCADE)


class ProductosXProveedores(models.Model):
    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    proveedor = models.ForeignKey(Proveedores, on_delete=models.CASCADE)


# --- INVENTARIO Y MOVIMIENTOS ---

class Stock(models.Model):
    producto = models.OneToOneField(Productos, on_delete=models.CASCADE)
    cantidad = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.producto.nombre} - Cantidad: {self.cantidad}"


class Alertas(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    mensaje = models.CharField(max_length=255)
    fecha = models.DateTimeField(auto_now_add=True)


class MovimientosStock(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    empleado = models.ForeignKey(Empleados, on_delete=models.CASCADE)
    tipo_movimiento = models.ForeignKey(TiposMovimientos, on_delete=models.CASCADE)
    cantidad = models.IntegerField()
    fecha = models.DateTimeField(auto_now_add=True)