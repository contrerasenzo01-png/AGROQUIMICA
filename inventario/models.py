# ============================================================
# MODELOS DEL SISTEMA · Agroquímica del Valle
#
# Cada clase de este archivo es una tabla de la base de datos MySQL.
# Django crea y modifica las tablas a partir de estas clases con
# los comandos "makemigrations" y "migrate".
#
#   - db_table:    nombre real de la tabla en MySQL.
#   - db_column:   nombre real de la columna (cuando difiere del atributo).
#   - ForeignKey:  clave foránea (relación muchos a uno).
#   - OneToOneField: relación uno a uno.
#   - ManyToManyField: relación muchos a muchos (usa una tabla intermedia).
#   - on_delete:   qué pasa con este registro si se borra el relacionado:
#       PROTECT -> no deja borrar el relacionado mientras existan registros.
#       CASCADE -> borra también estos registros.
#   - null=True:   la columna acepta NULL en la base.
#   - blank=True:  el campo puede quedar vacío en los formularios.
# ============================================================

from django.db import models
from django.utils import timezone


# ============================================================
# TIPOS DE PRODUCTOS
# Clasificación principal del catálogo: Fitosanitario,
# Fertilizante, Coadyuvante, etc.
# ============================================================

class TiposProductos(models.Model):
    # Clave primaria autoincremental.
    ID_Tipo_producto = models.AutoField(primary_key=True)

    # Nombre del tipo (por ejemplo "Fitosanitario").
    Nombre_tipo_producto = models.CharField(max_length=50)

    # Valores posibles del estado: se guarda True/False y se muestra
    # "Activo"/"Inactivo" en los formularios.
    ESTADO_CHOICES = [
        (True, 'Activo'),
        (False, 'Inactivo'),
    ]

    # Baja lógica: un tipo inactivo no se borra, solo deja de ofrecerse.
    Estado_tipo_producto = models.BooleanField(
        default=True,
        choices=ESTADO_CHOICES,
        verbose_name='Estado'
    )

    class Meta:
        db_table = 'TIPOS_PRODUCTOS'
        verbose_name_plural = 'Tipos de Productos'

    def __str__(self):
        # Texto que se muestra cuando se imprime el objeto.
        return self.Nombre_tipo_producto


# ============================================================
# SUBTIPOS
# Subdivisión de cada tipo: Fungicida, Herbicida, Insecticida...
# dentro de Fitosanitario.
# ============================================================

class Subtipos(models.Model):
    ID_Subtipo = models.AutoField(primary_key=True)

    # Tipo al que pertenece el subtipo.
    # Si se elimina el tipo, sus subtipos se eliminan con él (CASCADE).
    # La vista solo lo permite cuando ningún subtipo tiene productos.
    ID_Tipo_producto = models.ForeignKey(
        TiposProductos,
        on_delete=models.CASCADE,
        db_column='ID_Tipo_producto',
        related_name='subtipos'   # tipo.subtipos.all() devuelve sus subtipos
    )

    Nombre_subtipo = models.CharField(max_length=50)

    # Descripción opcional del subtipo.
    Descripcion_subtipo = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )

    class Meta:
        db_table = 'SUBTIPOS'
        verbose_name_plural = "Subtipos"

    def __str__(self):
        return self.Nombre_subtipo


# ============================================================
# PROVEEDORES
# Empresas que entregan la mercadería mediante remitos.
# ============================================================

class Proveedores(models.Model):
    ID_Proveedor = models.AutoField(
        primary_key=True,
        db_column='ID_Proveedor'
    )

    ESTADO_CHOICES = [
        (True, 'Activo'),
        (False, 'Inactivo'),
    ]

    # unique=True: no puede haber dos proveedores con el mismo nombre.
    nombre_proveedor = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nombre del Proveedor"
    )

    # Datos de contacto: todos opcionales.
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

    # Baja lógica: un proveedor inactivo no aparece al registrar remitos.
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
        """Dos letras para el círculo de la pantalla (ej.: "AgroBayer" -> "AG")."""

        palabras = self.nombre_proveedor.split()

        # Con dos palabras o más: primera letra de cada una.
        if len(palabras) >= 2:
            return f"{palabras[0][0]}{palabras[1][0]}".upper()

        # Con una sola palabra: sus dos primeras letras.
        return self.nombre_proveedor[:2].upper()


# ============================================================
# REMITOS (cabecera del proceso de ingreso de mercadería)
# Un remito tiene uno o varios lotes (tabla LOTES = detalle).
# ============================================================

class Remitos(models.Model):
    ID_Remito = models.AutoField(primary_key=True)

    # Proveedor que entregó la mercadería.
    # PROTECT: no se puede borrar un proveedor que tiene remitos.
    ID_Proveedor = models.ForeignKey(
        Proveedores,
        on_delete=models.PROTECT,
        db_column='ID_Proveedor',
        related_name='remitos'
    )

    # Número impreso en el remito del proveedor (ej.: R-0001-000042).
    Numero_remito = models.CharField(max_length=20)

    # Fecha que figura en el remito.
    Fecha_remito = models.DateField()

    ESTADO_CHOICES = [
        ('Confirmado', 'Confirmado'),
        ('Anulado', 'Anulado'),
    ]

    # Al registrarse queda "Confirmado"; si se anula pasa a "Anulado".
    # Los remitos nunca se borran.
    Estado_remito = models.CharField(
        max_length=10,
        choices=ESTADO_CHOICES,
        default='Confirmado'
    )

    # ---------------- DATOS DE LA ANULACIÓN ----------------
    # Quedan vacíos mientras el remito está confirmado.

    Fecha_anulacion = models.DateTimeField(
        null=True,
        blank=True
    )

    Motivo_anulacion = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    # Usuario que anuló el remito. Se escribe 'Usuarios' entre comillas
    # porque esa clase está definida más abajo en el archivo.
    ID_Usuario_anulacion = models.ForeignKey(
        'Usuarios',
        on_delete=models.PROTECT,
        db_column='ID_Usuario_anulacion',
        related_name='remitos_anulados',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'REMITOS'
        verbose_name = "Remito"
        verbose_name_plural = "Remitos"
        constraints = [
            # Un proveedor no puede repetir el mismo número de remito.
            models.UniqueConstraint(
                fields=['ID_Proveedor', 'Numero_remito'],
                name='uq_remito_proveedor_numero'
            )
        ]

    def __str__(self):
        return f"Remito {self.Numero_remito}"


# ============================================================
# TIPOS DE MOVIMIENTOS
# Entrada de lote, Egreso por venta, Salida por vencimiento de
# producto, Anulación de remito y Anulación de egreso.
# ============================================================

class TiposMovimientos(models.Model):
    ID_Tipo_movimiento = models.AutoField(primary_key=True)
    Nombre_tipo_movimiento = models.CharField(max_length=50)

    class Meta:
        db_table = 'TIPOS_MOVIMIENTOS'
        verbose_name_plural = "Tipos de Movimientos"

    def __str__(self):
        return self.Nombre_tipo_movimiento


# ============================================================
# PERFILES DE ACCESO
# Administrador, Vendedor, Secretaria... Cada perfil tiene un
# conjunto de permisos y cada usuario tiene un perfil.
# ============================================================

class Perfiles(models.Model):
    ID_Perfil = models.AutoField(primary_key=True)
    Nombre_perfil = models.CharField(max_length=50)

    ESTADO_CHOICES = [
        (True, 'Activo'),
        (False, 'Inactivo'),
    ]

    # Un perfil inactivo no puede ingresar al sistema.
    Estado_perfil = models.BooleanField(
        default=True,
        choices=ESTADO_CHOICES
    )

    # Relación muchos a muchos con PERMISOS a través de la tabla
    # intermedia PERFILES_X_PERMISOS (clase PerfilesXPermisos).
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


# ============================================================
# PERMISOS
# Catálogo de acciones del sistema (Gestionar productos,
# Anular remitos, etc.). Se cargan desde permissions.py.
# ============================================================

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


# ============================================================
# PERMISOS POR PERFIL (tabla intermedia)
# Cada fila dice: "este perfil tiene este permiso".
# ============================================================

class PerfilesXPermisos(models.Model):
    # Si se borra el perfil, se borran sus asignaciones de permisos.
    ID_Perfil = models.ForeignKey(
        Perfiles,
        on_delete=models.CASCADE,
        db_column='ID_Perfil'
    )

    # Si se borra el permiso, se borran sus asignaciones.
    ID_Permiso = models.ForeignKey(
        Permisos,
        on_delete=models.CASCADE,
        db_column='ID_Permiso'
    )

    class Meta:
        db_table = 'PERFILES_X_PERMISOS'
        # Un perfil no puede tener el mismo permiso dos veces.
        unique_together = (('ID_Perfil', 'ID_Permiso'),)
        verbose_name_plural = "Perfiles por Permisos"


# ============================================================
# USUARIOS
# Personas que ingresan al sistema.
# ============================================================

class Usuarios(models.Model):
    ID_Usuario = models.AutoField(primary_key=True)

    # Perfil del usuario. PROTECT: no se puede borrar un perfil
    # que tiene usuarios asignados.
    ID_Perfil = models.ForeignKey(
        Perfiles,
        on_delete=models.PROTECT,
        db_column='ID_Perfil',
        related_name='usuarios'
    )

    # El DNI no se puede repetir.
    DNI = models.IntegerField(unique=True)

    Apellido_usuario = models.CharField(max_length=50)

    Nombre_usuario = models.CharField(max_length=50)

    # Nombre para iniciar sesión (apellido + inicial del nombre).
    # No se puede repetir.
    Usuario = models.CharField(
        max_length=50,
        unique=True
    )

    # Contraseña encriptada con hash (nunca se guarda en texto plano).
    # En Python se llama "Contrasena" y en MySQL la columna es "Contraseña".
    Contrasena = models.CharField(
        max_length=255,
        db_column='Contraseña'
    )

    Email_usuario = models.EmailField(max_length=100)

    # Foto de perfil opcional. Se guarda en la carpeta media/usuarios/.
    Foto_usuario = models.ImageField(
        upload_to='usuarios/',
        blank=True,
        null=True,
        verbose_name='Foto de perfil'
    )

    # Baja lógica: un usuario inactivo no puede ingresar.
    Estado_usuario = models.BooleanField(default=True)

    # auto_now=True: se actualiza sola cada vez que se guarda el usuario.
    Fecha_ultima_modificacion = models.DateField(
        auto_now=True
    )

    # Fecha en que se dio de baja (vacía si está activo).
    Fecha_Baja = models.DateField(
        null=True,
        blank=True
    )

    # True cuando el usuario tiene una contraseña temporal y debe
    # cambiarla en su próximo inicio de sesión.
    Cambiar_contrasena = models.BooleanField(
        default=False,
        db_column='Cambiar_contraseña'
    )

    class Meta:
        db_table = 'USUARIOS'
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return (
            f"{self.Nombre_usuario} "
            f"{self.Apellido_usuario} ({self.Usuario})"
        )


# ============================================================
# PRODUCTOS
# Catálogo de productos que vende la agroquímica.
# ============================================================

class Productos(models.Model):
    ID_Producto = models.AutoField(primary_key=True)

    # Tipo del producto. PROTECT: un tipo o subtipo con productos
    # no se puede eliminar.
    ID_Tipo_producto = models.ForeignKey(
        TiposProductos,
        on_delete=models.PROTECT,
        db_column='ID_Tipo_producto'
    )

    # Subtipo opcional (solo si el tipo tiene subtipos).
    ID_Subtipo = models.ForeignKey(
        'Subtipos',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column='ID_Subtipo'
    )

    # El sistema no usa marca: un mismo producto puede venir de
    # varios proveedores, y el proveedor queda registrado en cada lote.
    Nombre_producto = models.CharField(max_length=50)

    # CharField: en un TextField el límite no se aplica en la base.
    Descripcion_producto = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )

    # Foto del producto (opcional). Se guarda en media/productos/.
    # views.py la achica a 1200 px y la convierte a WEBP.
    Imagen_producto = models.ImageField(
        upload_to='productos/',
        null=True,
        blank=True,
        verbose_name='Imagen'
    )

    # Precio de lista: hasta 8 dígitos enteros y 2 decimales.
    Precio = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # Presentación: cantidad y unidad (ej.: 1 litros, 20 kg).
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

    Unidades_por_presentacion = models.PositiveIntegerField(
        default=1,
        verbose_name='Unidades por presentación'
    )

    # Proveedores que suministran este producto.
    # Django crea la tabla intermedia PRODUCTOS_X_PROVEEDORES.
    proveedores = models.ManyToManyField(
        Proveedores,
        blank=True,
        related_name='productos',
        db_table='PRODUCTOS_X_PROVEEDORES',
        verbose_name='Proveedores'
    )

    ESTADO_CHOICES = [
        ('Activo', 'Activo'),
        ('Inactivo', 'Inactivo'),
    ]

    # Baja lógica: un producto inactivo no se puede vender ni recibir.
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


# ============================================================
# LOTES (detalle del remito)
# Cada lote es una partida de un producto con su fecha de vencimiento.
# ============================================================

class Lotes(models.Model):
    ID_Lote = models.AutoField(primary_key=True)

    # Remito con el que ingresó el lote.
    # Los lotes no se eliminan: conservan la trazabilidad
    # (remito de origen, movimientos y auditoría).
    ID_Remito = models.ForeignKey(
        Remitos,
        on_delete=models.PROTECT,
        db_column='ID_Remito',
        related_name='lotes',   # remito.lotes.all() devuelve sus lotes
    )

    # Producto del lote.
    ID_Producto = models.ForeignKey(
        Productos,
        on_delete=models.PROTECT,
        db_column='ID_Producto',
        related_name='lotes'
    )

    # Número de lote impreso en el envase.
    Numero_lote = models.CharField(max_length=50)

    # Cajas y unidades por caja: su producto es la cantidad ingresada.
    Cantidad_cajas = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Cantidad de cajas'
    )

    Unidades_por_caja = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Unidades por caja'
    )

    # Unidades que entraron con el remito (no cambia con las ventas).
    Cantidad_ingresada = models.IntegerField()

    # Unidades que quedan hoy en el lote (baja con cada egreso).
    Cantidad_actual = models.IntegerField()

    # Día en que se registró el ingreso en el sistema.
    Fecha_ingreso = models.DateField()

    Fecha_vencimiento = models.DateField()

    class Meta:
        db_table = 'LOTES'
        verbose_name_plural = "Lotes"
        constraints = [
            # Un producto no puede tener dos lotes con el mismo número.
            models.UniqueConstraint(
                fields=['ID_Producto', 'Numero_lote'],
                name='uq_lote_producto_numero'
            )
        ]

    @property
    def estado_actual(self):
        """Estado del lote (baja lógica, el lote nunca se elimina).

        El orden importa: un lote anulado o agotado se muestra así
        aunque después pase su fecha de vencimiento.
        """

        # 1) Su remito fue anulado.
        if self.ID_Remito.Estado_remito == 'Anulado':
            return 'Anulado'

        # 2) Ya no le quedan unidades.
        if self.Cantidad_actual <= 0:
            return 'Agotado'

        # 3) Tiene unidades pero ya pasó su fecha de vencimiento.
        if self.Fecha_vencimiento < timezone.localdate():
            return 'Vencido'

        # 4) Tiene unidades y está vigente.
        return 'Activo'

    def __str__(self):
        return self.Numero_lote


# ============================================================
# STOCK
# Un registro por producto con su stock total y su stock mínimo.
# ============================================================

class Stock(models.Model):
    ID_Stock = models.AutoField(primary_key=True)

    # Relación uno a uno: cada producto tiene un único stock.
    # Si se elimina el producto, se elimina su stock.
    ID_Producto = models.OneToOneField(
        Productos,
        on_delete=models.CASCADE,
        db_column='ID_Producto',
        related_name='stock'   # producto.stock devuelve su stock
    )

    # Suma de las unidades actuales de todos sus lotes.
    Cantidad_stock = models.IntegerField()

    # Al llegar a este valor o menos se genera la alerta de stock mínimo.
    Stock_minimo = models.IntegerField()

    class Meta:
        db_table = 'STOCK'
        verbose_name_plural = "Stock"

    def __str__(self):
        return (
            f"{self.ID_Producto.Nombre_producto} - "
            f"Stock: {self.Cantidad_stock}"
        )


# ============================================================
# HISTORIAL DE ALERTAS
# Alertas de stock mínimo y de vencimiento de lotes.
# ============================================================

class Alertas(models.Model):
    ID_Historial_alerta = models.AutoField(primary_key=True)

    # Stock (producto) al que se refiere la alerta.
    ID_Stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
        db_column='ID_Stock',
        related_name='alertas'
    )

    # "Stock mínimo" o "Vencimiento".
    Tipo_alerta = models.CharField(max_length=50)

    Mensaje = models.CharField(max_length=255)

    # auto_now_add=True: se completa sola al crear la alerta.
    Fecha_hora_historial_alerta = models.DateTimeField(
        auto_now_add=True
    )

    # Foto del momento: stock y mínimo cuando se generó la alerta.
    Cantidad_al_generar = models.IntegerField(
        null=True,
        blank=True
    )

    Stock_minimo_al_generar = models.IntegerField(
        null=True,
        blank=True
    )

    # Si alguien ya la atendió, cuándo y quién.
    Atendida = models.BooleanField(default=False)

    Fecha_hora_atencion = models.DateTimeField(
        null=True,
        blank=True
    )

    ID_Usuario = models.ForeignKey(
        Usuarios,
        on_delete=models.PROTECT,
        db_column='ID_Usuario',
        related_name='alertas_atendidas',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'HISTORIAL_ALERTAS'
        verbose_name_plural = "Historial de alertas"


# ============================================================
# MOVIMIENTOS DE STOCK
# Historial de todo lo que entra y sale: ingresos de lote,
# egresos por venta, egresos por vencimiento y anulaciones.
# ============================================================

class MovimientosStock(models.Model):
    ID_Movimiento_stock = models.AutoField(primary_key=True)

    # Usuario que registró el movimiento.
    ID_Usuario = models.ForeignKey(
        Usuarios,
        on_delete=models.PROTECT,
        db_column='ID_Usuario'
    )

    # Tipo de movimiento (Entrada de lote, Egreso por venta, etc.).
    ID_Tipo_movimiento = models.ForeignKey(
        TiposMovimientos,
        on_delete=models.PROTECT,
        db_column='ID_Tipo_movimiento'
    )

    # Lote afectado por el movimiento.
    ID_Lote = models.ForeignKey(
        Lotes,
        on_delete=models.PROTECT,
        db_column='ID_Lote',
        related_name='movimientos',
        null=True,
        blank=True
    )

    # Fecha y hora del movimiento: se completa sola al crearlo.
    Fecha_hora_movimiento = models.DateTimeField(
        auto_now_add=True
    )

    # Cantidad de unidades (siempre positiva; el tipo dice si suma o resta).
    Cantidad_movimiento_stock = models.IntegerField()

    # Detalle libre. En una anulación de egreso indica qué egreso anuló
    # (ej.: "Anulación del egreso N.º 123: motivo").
    Observaciones = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    # ---------------- ANULACIÓN DE EGRESOS ----------------
    # Un egreso hecho por error no se borra: se marca como anulado
    # y se genera un movimiento de "Anulación de egreso".
    # Para que un egreso no se anule dos veces, la vista bloquea el
    # registro (select_for_update) y revisa el campo Anulado.

    Anulado = models.BooleanField(default=False)

    Fecha_anulacion = models.DateTimeField(
        null=True,
        blank=True
    )

    Motivo_anulacion = models.CharField(
        max_length=200,
        null=True,
        blank=True
    )

    # Usuario que anuló el egreso.
    ID_Usuario_anulacion = models.ForeignKey(
        Usuarios,
        on_delete=models.PROTECT,
        db_column='ID_Usuario_anulacion',
        related_name='movimientos_anulados',
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


# ============================================================
# LOG DE AUDITORÍA
# Registro de cada alta, modificación, baja o anulación:
# quién la hizo, cuándo, en qué sección y qué valores cambiaron.
# ============================================================

class LogAuditoria(models.Model):
    ID_Log = models.AutoField(primary_key=True)

    # Usuario que realizó la acción.
    ID_Usuario = models.ForeignKey(
        Usuarios,
        on_delete=models.PROTECT,
        db_column='ID_Usuario',
        related_name='auditorias'
    )

    # Fecha y hora de la acción (se completa sola).
    Fecha_hora = models.DateTimeField(auto_now_add=True)

    # Sección del sistema: Productos, Remitos, Usuarios, etc.
    Seccion = models.CharField(max_length=50)

    # ID del registro afectado dentro de esa sección.
    ID_Registro = models.IntegerField()

    # Acción realizada: CREACION, MODIFICACION, ANULACION, BAJA...
    # 30 caracteres: margen para acciones con nombre largo
    # (por ejemplo RECUPERA_CONTRASENA o ASIGNACION_PERMISOS).
    Accion = models.CharField(max_length=30)

    # Datos antes y después del cambio, guardados en formato JSON.
    Valores_anteriores = models.JSONField(default=dict)
    Valores_actuales = models.JSONField(default=dict)

    class Meta:
        db_table = 'LOG_AUDITORIA'
        verbose_name_plural = "Log de auditoría"
        # Por defecto, los registros más nuevos primero.
        ordering = ['-Fecha_hora']

    @property
    def cambios(self):
        """Lista de (campo, valor anterior, valor actual) de los campos que cambiaron."""

        ant = self.Valores_anteriores or {}
        act = self.Valores_actuales or {}

        return [
            (campo, ant.get(campo), act.get(campo))
            # Todos los campos que aparecen antes o después, ordenados.
            for campo in sorted(set(ant) | set(act))
            # Solo los que tienen un valor distinto.
            if ant.get(campo) != act.get(campo)
        ]


# ============================================================
# CONFIGURACIONES (umbrales de las reglas de alertas)
# Los valores se editan desde la pantalla "Configuración de alertas";
# las reglas los leen de esta tabla, no están fijos en el código.
# ============================================================

class Configuracion(models.Model):
    ID_Configuracion = models.AutoField(primary_key=True)

    # Nombre del parámetro (ej.: dias_aviso_vencimiento). No se repite.
    Clave = models.CharField(max_length=50, unique=True)

    # Valor del parámetro (ej.: "30").
    Valor = models.CharField(max_length=100)

    # Explicación del parámetro para la pantalla.
    Descripcion = models.CharField(max_length=255, blank=True, default='')

    # auto_now=True: se actualiza cada vez que se modifica el valor.
    Fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'CONFIGURACIONES'
        verbose_name = 'Configuración'
        verbose_name_plural = 'Configuraciones'

    def __str__(self):
        return f'{self.Clave} = {self.Valor}'


# ============================================================
# NOTIFICACIONES (bandeja del header)
# Cada regla de alerta deja una notificación por perfil destinatario.
# "Clave" identifica el evento que la disparó: con la restricción
# única (Clave, Destino_perfil) un mismo evento no se notifica dos veces.
# La notificación va dirigida al perfil (no a un usuario): cada usuario
# ve las de su perfil, por eso no hay relación directa con USUARIOS.
# ============================================================

class Notificacion(models.Model):
    ID_Notificacion = models.AutoField(primary_key=True)

    # Fecha y hora en que se generó (se completa sola).
    Fecha = models.DateTimeField(auto_now_add=True)

    # Tipo de aviso: stock mínimo, vencimiento, egreso inusual...
    Tipo = models.CharField(max_length=50)

    Mensaje = models.CharField(max_length=255)

    # Perfil que recibe la notificación.
    Destino_perfil = models.ForeignKey(
        Perfiles,
        on_delete=models.CASCADE,
        db_column='Destino_perfil',
        related_name='notificaciones'
    )

    # Si ya se leyó y cuándo.
    Leida = models.BooleanField(default=False)
    Fecha_lectura = models.DateTimeField(null=True, blank=True)

    # Identificador del evento que generó la notificación.
    Clave = models.CharField(max_length=100)

    class Meta:
        db_table = 'NOTIFICACIONES'
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'
        # Las más nuevas primero.
        ordering = ['-Fecha']
        constraints = [
            # Un mismo evento no se notifica dos veces al mismo perfil.
            models.UniqueConstraint(
                fields=['Clave', 'Destino_perfil'],
                name='uq_notificacion_clave_perfil'
            )
        ]

    def __str__(self):
        return f'{self.Tipo}: {self.Mensaje[:40]}'
    