from django.db import models


class TiposProductos(models.Model):
    ID_Tipo_producto = models.AutoField(primary_key=True)
    Nombre_tipo_producto = models.CharField(max_length=50)

    ESTADO_CHOICES = [
        (True, 'Activo'),
        (False, 'Inactivo'),
    ]

    Estado_tipo_producto = models.BooleanField(
        default=True,
        choices=ESTADO_CHOICES
    )

    class Meta:
        db_table = 'TIPOS_PRODUCTOS'
        verbose_name_plural = "Tipos de Productos"

    def __str__(self):
        return self.Nombre_tipo_producto


class Subtipos(models.Model):
    ID_Subtipo = models.AutoField(primary_key=True)

    ID_Tipo_producto = models.ForeignKey(
        TiposProductos,
        on_delete=models.CASCADE,
        db_column='ID_Tipo_producto',
        related_name='subtipos'
    )

    Nombre_subtipo = models.CharField(max_length=50)

    ESTADO_CHOICES = [
        (True, 'Activo'),
        (False, 'Inactivo'),
    ]

    Estado_subtipo = models.BooleanField(
        default=True,
        choices=ESTADO_CHOICES
    )

    class Meta:
        db_table = 'SUBTIPOS'
        verbose_name_plural = "Subtipos"

    def __str__(self):
        return self.Nombre_subtipo


class Proveedores(models.Model):
    ID_Proveedor = models.AutoField(
        primary_key=True,
        db_column='ID_Proveedor'
    )

    ESTADO_CHOICES = [
        (True, 'Activo'),
        (False, 'Inactivo'),
    ]

    nombre_proveedor = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nombre del Proveedor"
    )

    telefono_proveedor = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Teléfono"
    )

    email_proveedor = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email"
    )

    direccion_proveedor = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Dirección"
    )

    estado_proveedor = models.BooleanField(
        default=True,
        choices=ESTADO_CHOICES,
        verbose_name="Estado"
    )

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


class TiposMovimientos(models.Model):
    ID_Tipo_movimiento = models.AutoField(primary_key=True)
    Nombre_tipo_movimiento = models.CharField(max_length=50)

    class Meta:
        db_table = 'TIPOS_MOVIMIENTOS'
        verbose_name_plural = "Tipos de Movimientos"

    def __str__(self):
        return self.Nombre_tipo_movimiento


class Perfiles(models.Model):
    ID_Perfil = models.AutoField(primary_key=True)
    Nombre_perfil = models.CharField(max_length=50)

    ESTADO_CHOICES = [
        (True, 'Activo'),
        (False, 'Inactivo'),
    ]

    Estado_perfil = models.BooleanField(
        default=True,
        choices=ESTADO_CHOICES
    )

    permisos = models.ManyToManyField(
        'Permisos',
        through='PerfilesXPermisos',
        related_name='perfiles'
    )

    class Meta:
        db_table = 'PERFILES'
        verbose_name_plural = "Perfiles"

    def __str__(self):
        return self.Nombre_perfil


class Permisos(models.Model):
    ID_Permiso = models.AutoField(primary_key=True)
    Nombre_permiso = models.CharField(max_length=100)

    Descripcion_permiso = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    class Meta:
        db_table = 'PERMISOS'
        verbose_name_plural = "Permisos"

    def __str__(self):
        return self.Nombre_permiso


class PerfilesXPermisos(models.Model):
    ID_Perfil = models.ForeignKey(
        Perfiles,
        on_delete=models.CASCADE,
        db_column='ID_Perfil'
    )

    ID_Permiso = models.ForeignKey(
        Permisos,
        on_delete=models.CASCADE,
        db_column='ID_Permiso'
    )

    class Meta:
        db_table = 'PERFILES_X_PERMISOS'
        unique_together = (('ID_Perfil', 'ID_Permiso'),)
        verbose_name_plural = "Perfiles por Permisos"


class Usuarios(models.Model):
    ID_Usuario = models.AutoField(primary_key=True)

    ID_Perfil = models.ForeignKey(
        Perfiles,
        on_delete=models.PROTECT,
        db_column='ID_Perfil'
    )

    DNI = models.IntegerField(unique=True)

    Apellido_usuario = models.CharField(max_length=50)

    Nombre_usuario = models.CharField(max_length=50)

    Usuario = models.CharField(
        max_length=50,
        unique=True
    )

    Contrasena = models.CharField(
        max_length=255,
        db_column='Contraseña'
    )

    Email_usuario = models.EmailField(max_length=100)

    Estado_usuario = models.BooleanField(default=True)

    Fecha_ultima_modificacion = models.DateField(
        auto_now=True
    )

    Fecha_Baja = models.DateField(
        null=True,
        blank=True
    )

    Cambiar_contrasena = models.BooleanField(
        default=False,
        db_column='Cambiar_contraseña'
    )

    class Meta:
        db_table = 'USUARIOS'
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return f"{self.Nombre_usuario} {self.Apellido_usuario} ({self.Usuario})"


class Productos(models.Model):
    ID_Producto = models.AutoField(primary_key=True)

    ID_Tipo_producto = models.ForeignKey(
        TiposProductos,
        on_delete=models.CASCADE,
        db_column='ID_Tipo_producto'
    )

    Marca = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    Nombre_producto = models.CharField(max_length=50)

    Descripcion_producto = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    Precio = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    Cantidad_presentacion = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    Unidad_medida_producto = models.CharField(
        max_length=20,
        null=True,
        blank=True
    )

    ESTADO_CHOICES = [
        ('Activo', 'Activo'),
        ('Inactivo', 'Inactivo'),
    ]

    Estado_producto = models.CharField(
        max_length=10,
        choices=ESTADO_CHOICES,
        default='Activo'
    )

    class Meta:
        db_table = 'PRODUCTOS'
        verbose_name_plural = "Productos"

    def __str__(self):
        return self.Nombre_producto


class Lotes(models.Model):
    ID_Lote = models.AutoField(primary_key=True)

    ID_Proveedor = models.ForeignKey(
        Proveedores,
        on_delete=models.PROTECT,
        db_column='ID_Proveedor',
        related_name='lotes'
    )

    ID_Producto = models.ForeignKey(
        Productos,
        on_delete=models.CASCADE,
        db_column='ID_Producto',
        related_name='lotes'
    )

    Numero_lote = models.CharField(max_length=50)

    Cantidad_ingresada = models.IntegerField()

    Cantidad_actual = models.IntegerField()

    Fecha_ingreso = models.DateField()

    Fecha_vencimiento = models.DateField(
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'LOTES'
        verbose_name_plural = "Lotes"

    def __str__(self):
        return self.Numero_lote


class Stock(models.Model):
    ID_Stock = models.AutoField(primary_key=True)

    ID_Producto = models.OneToOneField(
        Productos,
        on_delete=models.CASCADE,
        db_column='ID_Producto',
        related_name='stock'
    )

    Cantidad_stock = models.IntegerField()

    Stock_minimo = models.IntegerField()

    class Meta:
        db_table = 'STOCK'
        verbose_name_plural = "Stock"

    def __str__(self):
        return (
            f"{self.ID_Producto.Nombre_producto} - "
            f"Stock: {self.Cantidad_stock}"
        )


class Alertas(models.Model):
    ID_Historial_alerta = models.AutoField(primary_key=True)

    ID_Lote = models.ForeignKey(
        Lotes,
        on_delete=models.CASCADE,
        db_column='ID_Lote',
        related_name='alertas',
        null=True,
        blank=True
    )

    ID_Stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
        db_column='ID_Stock',
        related_name='alertas'
    )

    Tipo_alerta = models.CharField(max_length=50)

    Mensaje = models.CharField(max_length=255)

    Fecha_hora_historial_alerta = models.DateTimeField(
        auto_now_add=True
    )

    Cantidad_al_generar = models.IntegerField(
        null=True,
        blank=True
    )

    Stock_minimo_al_generar = models.IntegerField(
        null=True,
        blank=True
    )

    Atendida = models.BooleanField(
        default=False
    )

    Fecha_hora_atencion = models.DateTimeField(
        null=True,
        blank=True
    )

    ID_Usuario = models.ForeignKey(
        Usuarios,
        on_delete=models.SET_NULL,
        db_column='ID_Usuario',
        related_name='alertas_atendidas',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'HISTORIAL_ALERTAS'
        verbose_name_plural = "Historial de alertas"


class MovimientosStock(models.Model):
    ID_Movimiento_stock = models.AutoField(primary_key=True)

    ID_Usuario = models.ForeignKey(
        Usuarios,
        on_delete=models.CASCADE,
        db_column='ID_Usuario'
    )

    ID_Tipo_movimiento = models.ForeignKey(
        TiposMovimientos,
        on_delete=models.CASCADE,
        db_column='ID_Tipo_movimiento'
    )

    ID_Lote = models.ForeignKey(
        Lotes,
        on_delete=models.PROTECT,
        db_column='ID_Lote',
        related_name='movimientos',
        null=True,
        blank=True
    )

    Fecha_hora_movimiento = models.DateTimeField(
        auto_now_add=True
    )

    Cantidad_movimiento_stock = models.IntegerField()

    Observaciones = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'MOVIMIENTOS_STOCK'
        verbose_name_plural = "Movimientos de Stock"

    def __str__(self):
        return (
            f"Movimiento {self.ID_Movimiento_stock} - "
            f"{self.Cantidad_movimiento_stock} unidades"
        )