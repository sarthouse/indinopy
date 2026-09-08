from django.db import models
from django.contrib.auth.models import User

class Categoria(models.Model):
    nombre = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategorias')

    def __str__(self):
        return self.nombre

class ProductoTemplate(models.Model):
    TIPO_PRODUCTO_CHOICES = [
        ('almacenable', 'Almacenable (Storable)'),
        ('consumible', 'Consumible (Consumable)'),
        ('servicio', 'Servicio (Service)'),
    ]
    UNIDAD_MEDIDA_CHOICES = [
        ('unidades', 'Unidades'),
        ('pares', 'Pares'),
        ('metros', 'Metros'),
        ('kg', 'Kilogramos'),
        ('horas', 'Horas'),
        ('minutos', 'Minutos'),
        ('litros', 'Litros'),
    ]

    nombre = models.CharField(max_length=200)
    codigo_interno = models.CharField(max_length=50, unique=True, null=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True)
    descripcion = models.TextField(blank=True, null=True)
    tipo_producto = models.CharField(max_length=20, choices=TIPO_PRODUCTO_CHOICES, default='almacenable')
    unidad_medida = models.CharField(max_length=20, choices=UNIDAD_MEDIDA_CHOICES, default='unidades', help_text="Ej: Unidades, Metros, Kg, Horas")
    
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    costo = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # Define si el producto se trackea por lote, número de serie, o nada
    TRACKING_CHOICES = [
        ('none', 'Sin seguimiento'),
        ('lote', 'Por Lotes'),
        ('serie', 'Por Número de Serie Unico'),
    ]
    tracking = models.CharField(max_length=10, choices=TRACKING_CHOICES, default='none')
    
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class Atributo(models.Model):
    nombre = models.CharField(max_length=50) # Ej: Talle, Color

    def __str__(self):
        return self.nombre

class AtributoValor(models.Model):
    atributo = models.ForeignKey(Atributo, on_delete=models.CASCADE, related_name='valores')
    valor = models.CharField(max_length=50) # Ej: 39, 40, Negro, Marrón

    def __str__(self):
        return f"{self.atributo.nombre}: {self.valor}"

class Producto(models.Model):
    template = models.ForeignKey(ProductoTemplate, on_delete=models.CASCADE, related_name='variantes')
    valores_atributo = models.ManyToManyField(AtributoValor, blank=True)
    
    sku = models.CharField(max_length=100, unique=True)
    codigo_barras = models.CharField(max_length=100, blank=True, null=True)
    
    # El recargo que tiene esta variante específica sobre el precio base del template
    precio_extra = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) 

    def __str__(self):
        if self.valores_atributo.exists():
            atributos_str = " - ".join([av.valor for av in self.valores_atributo.all()])
            return f"{self.template.nombre} ({atributos_str})"
        return self.template.nombre

# ==========================================
# MOTOR DE INVENTARIO (PARTIDA DOBLE, QUANTS Y LOTES)
# ==========================================

class Ubicacion(models.Model):
    TIPO_UBICACION_CHOICES = [
        ('interna', 'Ubicación Física'),
        ('proveedor', 'Virtual: Proveedor'),
        ('cliente', 'Virtual: Cliente'),
        ('produccion', 'Virtual: Producción'),
        ('ajuste', 'Virtual: Ajuste/Pérdida'),
    ]
    
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPO_UBICACION_CHOICES)
    activa = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre}"

class Lote(models.Model):
    """Identifica un lote específico de manufactura o compra para un Producto"""
    numero = models.CharField(max_length=100, unique=True, help_text="Ej: LOTE-24-10-A")
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='lotes')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    referencia_externa = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.numero

class StockQuant(models.Model):
    """
    La "foto" actual (Snapshot).
    Evita tener que sumar miles de movimientos cada vez que quieres ver el stock.
    Se actualiza automáticamente cuando un MovimientoStock pasa a estado 'realizado'.
    """
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    ubicacion = models.ForeignKey(Ubicacion, on_delete=models.CASCADE)
    lote = models.ForeignKey(Lote, on_delete=models.CASCADE, blank=True, null=True)
    
    cantidad_fisica = models.DecimalField(max_digits=12, decimal_places=4, default=0.0)
    cantidad_reservada = models.DecimalField(max_digits=12, decimal_places=4, default=0.0)
    
    class Meta:
        # Solo puede haber un quant (registro) por combinación exacta de producto + ubicacion + lote
        unique_together = ('producto', 'ubicacion', 'lote')

    def __str__(self):
        lote_str = f" [Lote: {self.lote.numero}]" if self.lote else ""
        return f"{self.cantidad_fisica} {self.producto.template.unidad_medida} - {self.producto}{lote_str} en {self.ubicacion.nombre}"

class MovimientoStock(models.Model):
    """
    Cabecera (Agrupador de líneas). El documento físico. (Odoo: stock.picking)
    """
    TIPO_MOVIMIENTO_CHOICES = [
        ('recepcion', 'Recepción (Ingreso)'),
        ('entrega', 'Entrega (Salida)'),
        ('traslado', 'Traslado Interno'),
    ]

    numero = models.CharField(max_length=50, unique=True, help_text="Ej: M-0001-00001234")
    tipo = models.CharField(max_length=20, choices=TIPO_MOVIMIENTO_CHOICES)
    es_fiscal = models.BooleanField(default=False)
    
    # Ubicaciones globales por defecto para este documento
    ubicacion_origen = models.ForeignKey(Ubicacion, on_delete=models.RESTRICT, related_name='movimientos_origen')
    ubicacion_destino = models.ForeignKey(Ubicacion, on_delete=models.RESTRICT, related_name='movimientos_destino')
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    responsable = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.numero} ({self.get_tipo_display()})"


class LineaMovimientoStock(models.Model):
    """
    La línea específica que mueve una cantidad de producto (Odoo: stock.move).
    """
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('reservado', 'Reservado (Impacta Quant Reservado)'),
        ('realizado', 'Realizado (Impacta Quant Físico)'),
        ('cancelado', 'Cancelado'),
    ]

    movimiento = models.ForeignKey(MovimientoStock, on_delete=models.CASCADE, related_name='lineas')
    
    producto = models.ForeignKey(Producto, on_delete=models.RESTRICT)
    cantidad = models.DecimalField(max_digits=12, decimal_places=4)
    lote = models.ForeignKey(Lote, on_delete=models.RESTRICT, blank=True, null=True, help_text="Obligatorio si el producto trackea por lote")
    
    # Redundancia intencional (explicación en el chat):
    # Por defecto, heredan de MovimientoStock, pero permiten granularidad (Ej: sacar de estantes distintos)
    ubicacion_origen = models.ForeignKey(Ubicacion, on_delete=models.RESTRICT, related_name='lineas_salida', blank=True, null=True)
    ubicacion_destino = models.ForeignKey(Ubicacion, on_delete=models.RESTRICT, related_name='lineas_entrada', blank=True, null=True)
    
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    fecha_efectiva = models.DateTimeField(blank=True, null=True)
    responsable = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    referencia = models.CharField(max_length=100, help_text="Ej: OP-001, Factura-X, Ajuste-2024")
    
    def save(self, *args, **kwargs):
        # Autocompletar ubicaciones desde la cabecera si están vacías
        if not self.ubicacion_origen and self.movimiento:
            self.ubicacion_origen = self.movimiento.ubicacion_origen
        if not self.ubicacion_destino and self.movimiento:
            self.ubicacion_destino = self.movimiento.ubicacion_destino
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cantidad} {self.producto} ({self.estado})"
