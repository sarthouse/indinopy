from django.db import models
from django.contrib.auth.models import User
from apps.almacen.models import ProductoTemplate, Producto

class Receta(models.Model):
    """Ficha Técnica (BOM). Define cómo se fabrica un Producto genérico."""
    producto_template = models.ForeignKey(ProductoTemplate, on_delete=models.CASCADE, related_name='recetas')
    nombre_version = models.CharField(max_length=100)
    observaciones_generales = models.TextField(blank=True, null=True)
    activa = models.BooleanField(default=True)

    def __str__(self):
        return f"Receta: {self.producto_template.nombre} ({self.nombre_version})"

class RecetaInsumo(models.Model):
    receta = models.ForeignKey(Receta, on_delete=models.CASCADE, related_name='insumos')
    insumo = models.ForeignKey(ProductoTemplate, on_delete=models.RESTRICT)
    cantidad_base = models.DecimalField(max_digits=10, decimal_places=4)

    def __str__(self):
        return f"{self.insumo.nombre} - {self.cantidad_base}"

class RecetaEtapa(models.Model):
    receta = models.ForeignKey(Receta, on_delete=models.CASCADE, related_name='etapas')
    orden_ejecucion = models.PositiveIntegerField()
    servicio = models.ForeignKey(ProductoTemplate, on_delete=models.RESTRICT)
    observaciones_proceso = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['orden_ejecucion']

    def __str__(self):
        return f"{self.orden_ejecucion}. {self.servicio.nombre}"

# ==========================================
# MODELOS DE EJECUCIÓN (PRODUCCIÓN REAL)
# ==========================================

class OrdenProduccion(models.Model):
    ESTADO_CHOICES = [
        ('borrador', 'Borrador / Pendiente'),
        ('en_proceso', 'En Proceso'),
        ('finalizada', 'Finalizada (En Almacén)'),
        ('cancelada', 'Cancelada'),
    ]
    
    # Subestados granulares de manufactura
    SUBESTADO_CHOICES = [
        ('espera', 'En Espera'),
        ('cortado', 'En Cortado'),
        ('rebajado', 'En Rebajado'),
        ('aparado', 'En Aparado'),
        ('armado', 'En Armado'),
    ]
    
    TIPO_PRODUCCION = [
        ('interna', 'Producción Interna / Talleres controlados'),
        ('fason', 'A Fasón (Tercerización completa)'),
    ]

    numero_op = models.CharField(max_length=20, unique=True)
    fecha_emision = models.DateField(auto_now_add=True)
    fecha_entrega = models.DateField(blank=True, null=True)
    
    receta_base = models.ForeignKey(Receta, on_delete=models.RESTRICT)
    cantidad_total = models.PositiveIntegerField()
    
    tipo = models.CharField(max_length=20, choices=TIPO_PRODUCCION, default='interna', help_text="Define si controlamos el stock o lo maneja el fasón")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    subestado = models.CharField(max_length=20, choices=SUBESTADO_CHOICES, default='espera')

    class Meta:
        permissions = [
            ("view_costos_op", "Puede ver los costos e insumos valorizados de la OP"),
            ("aprobar_op", "Puede pasar una OP a En Proceso"),
        ]

    def __str__(self):
        return f"OP {self.numero_op} - {self.receta_base.producto_template.nombre}"

class OPVariacion(models.Model):
    op = models.ForeignKey(OrdenProduccion, on_delete=models.CASCADE, related_name='variaciones')
    producto = models.ForeignKey(Producto, on_delete=models.RESTRICT)
    cantidad = models.PositiveIntegerField()

class OPInsumoRequerido(models.Model):
    ORIGEN_INSUMO_CHOICES = [
        ('empresa', 'Stock Propio (Descuenta Almacén)'),
        ('fabrica', 'Provisto por Taller/Fasón (Genera Deuda posterior)'),
    ]

    op = models.ForeignKey(OrdenProduccion, on_delete=models.CASCADE, related_name='insumos_requeridos')
    insumo = models.ForeignKey(ProductoTemplate, on_delete=models.RESTRICT)
    
    origen = models.CharField(max_length=20, choices=ORIGEN_INSUMO_CHOICES, default='empresa')
    cantidad_teorica = models.DecimalField(max_digits=10, decimal_places=4)
    cantidad_consumida_real = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    costo_facturado_fason = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Costo cargado posteriormente por el fasón si ellos compraron el insumo")

class OPEtapaTracking(models.Model):
    ESTADO_ETAPA_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('en_curso', 'En Curso'),
        ('pausada', 'Pausada / Problema'),
        ('finalizada', 'Finalizada'),
    ]

    op = models.ForeignKey(OrdenProduccion, on_delete=models.CASCADE, related_name='tracking_etapas')
    etapa_origen = models.ForeignKey(RecetaEtapa, on_delete=models.RESTRICT)
    
    tallerista_real = models.CharField(max_length=100, blank=True, null=True)
    responsable_interno = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, help_text="Usuario de Indino encargado de auditar esta etapa")
    
    estado = models.CharField(max_length=20, choices=ESTADO_ETAPA_CHOICES, default='pendiente')
    costo_servicio_total = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

class OPEtapaLog(models.Model):
    """Log inmutable de cambios y observaciones en el tracking de etapas."""
    etapa_tracking = models.ForeignKey(OPEtapaTracking, on_delete=models.CASCADE, related_name='logs')
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, help_text="Quien registró el cambio")
    
    estado_anterior = models.CharField(max_length=20, blank=True, null=True)
    estado_nuevo = models.CharField(max_length=20)
    observacion = models.TextField(help_text="Ej: 'Faltó hilo blanco', 'Se entregó al tallerista'")

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.fecha.strftime('%d/%m %H:%M')} - {self.usuario} - {self.estado_nuevo}"
