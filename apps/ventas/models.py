from django.db import models
from apps.base.models import DocumentoBase, TimeStampedModel
from apps.inventario.models import Producto, Ubicacion
from apps.base.models import ConfiguracionEmpresa

class TiendaWooCommerce(TimeStampedModel):
    """Configuración y credenciales de cada tienda WooCommerce conectada (Multi-Tenant)."""
    empresa = models.ForeignKey(ConfiguracionEmpresa, on_delete=models.CASCADE, related_name="tiendas_woocommerce")
    nombre = models.CharField(max_length=100, unique=True, help_text="Ej: Tienda Oficial B2C")
    codigo_prefijo = models.CharField(max_length=10, unique=True, help_text="Ej: WC-B2C")
    url = models.URLField(help_text="https://mitienda.com")
    consumer_key = models.CharField(max_length=100)
    consumer_secret = models.CharField(max_length=100) 
    webhook_secret = models.CharField(max_length=100, blank=True)
    activa = models.BooleanField(default=True)
    
    almacen_origen = models.ForeignKey(
        Ubicacion,
        on_delete=models.RESTRICT,
        help_text="Ubicación física de stock de donde se reserva/despacha esta tienda",
        null=True, blank=True
    )
    sincronizar_stock = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} ({self.codigo_prefijo})"


class OrdenVenta(DocumentoBase):
    """
    Representa un Pedido de Venta (B2C o B2B).
    Genera remitos de salida y facturas de venta.
    """
    tienda = models.ForeignKey(
        TiendaWooCommerce,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes"
    )
    wc_order_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    wc_order_number = models.CharField(max_length=50, blank=True)
    wc_status = models.CharField(max_length=50, blank=True)

    cliente = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        related_name="ordenes_venta"
    )
    
    # Totales monetarios desglosados
    subtotal_productos = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    total_descuentos = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    total_envio = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    total_recargos_fees = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    total_impuestos = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    monto_total = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)

    # Logística y método de pago
    metodo_envio_titulo = models.CharField(max_length=200, blank=True)
    metodo_envio_id = models.CharField(max_length=100, blank=True)
    metodo_pago = models.CharField(max_length=100, blank=True)
    transaccion_id = models.CharField(max_length=150, blank=True)
    cupones_aplicados = models.JSONField(default=list, blank=True) # [{code, discount}]
    
    # Metadatos flexibles no mapeados a columnas
    datos_adicionales_meta = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Orden de Venta"
        verbose_name_plural = "Órdenes de Venta"
        unique_together = [("tienda", "wc_order_id")]


class LineaOrdenVenta(models.Model):
    orden = models.ForeignKey(OrdenVenta, on_delete=models.CASCADE, related_name="lineas")
    producto = models.ForeignKey(Producto, on_delete=models.RESTRICT)
    wc_line_id = models.PositiveBigIntegerField(null=True, blank=True)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=15, decimal_places=2)
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    descuento = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    total_linea = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)

    def save(self, *args, **kwargs):
        self.subtotal = self.cantidad * self.precio_unitario
        self.total_linea = self.subtotal - self.descuento
        super().save(*args, **kwargs)


class LineaRecargoOrden(models.Model):
    """Mapeo de fee_lines para recargos de pasarelas (MercadoPago) o servicios extra."""
    orden = models.ForeignKey(OrdenVenta, on_delete=models.CASCADE, related_name="recargos")
    nombre = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=15, decimal_places=2)
    impuesto = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
