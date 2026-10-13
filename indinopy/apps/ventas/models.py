from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.base.models import DocumentoBase, TimeStampedModel, Moneda
from apps.inventario.models import Producto, Ubicacion
from apps.base.models import ConfiguracionEmpresa


class ListaPrecio(TimeStampedModel):
    """
    Lista de precios de venta (Pricelist).
    Permite definir tarifas diferenciadas (ej. Mayorista, Minorista, Distribuidores, Moneda Extranjera).
    """

    nombre = models.CharField(max_length=100, unique=True, verbose_name=_("Nombre"))
    codigo = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        verbose_name=_("Código identificador"),
        help_text=_("Ej: MAY-ARS, MIN-USD, DIST-01"),
    )
    moneda = models.ForeignKey(
        Moneda,
        on_delete=models.RESTRICT,
        related_name="listas_precio",
        verbose_name=_("Moneda"),
    )
    descripcion = models.TextField(blank=True, verbose_name=_("Descripción"))
    activa = models.BooleanField(default=True, verbose_name=_("Activa"))

    class Meta:
        verbose_name = _("Lista de Precios")
        verbose_name_plural = _("Listas de Precios")
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.moneda.codigo})"

    def obtener_precio(self, producto):
        """
        Retorna el precio unitario del producto en esta lista.
        Si no se encuentra un ítem específico para la variante,
        se utiliza el fallback base (template.precio + producto.precio_extra).
        """
        item = self.items.filter(producto=producto).first()
        if item:
            return item.precio_unitario
        base_precio = getattr(producto.template, "precio", 0)
        extra = getattr(producto, "precio_extra", 0)
        return base_precio + extra


class ItemListaPrecio(TimeStampedModel):
    """
    Precio fijado para una variante de producto en una Lista de Precios determinada.
    """

    lista = models.ForeignKey(
        ListaPrecio,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Lista de precios"),
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="precios_en_listas",
        verbose_name=_("Producto (Variante/SKU)"),
    )
    precio_unitario = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        verbose_name=_("Precio unitario"),
    )
    cantidad_minima = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=1.0,
        verbose_name=_("Cantidad mínima"),
        help_text=_("Aplica a partir de esta cantidad pedida"),
    )
    vigencia_desde = models.DateField(
        null=True, blank=True, verbose_name=_("Vigencia desde")
    )
    vigencia_hasta = models.DateField(
        null=True, blank=True, verbose_name=_("Vigencia hasta")
    )

    class Meta:
        verbose_name = _("Ítem de Lista de Precios")
        verbose_name_plural = _("Ítems de Listas de Precios")
        unique_together = ("lista", "producto", "cantidad_minima")
        ordering = ["lista", "producto", "cantidad_minima"]

    def __str__(self):
        return f"{self.producto.sku} - {self.lista.nombre}: {self.precio_unitario}"

class CanalVenta(TimeStampedModel):
    """
    Canal de origen de la venta (ej. 'WooCommerce B2C', 'MercadoLibre Oficial', 'Mostrador Fábrica').
    Aísla al ERP del proveedor de ecommerce o canal de comercialización.
    """
    TIPO_CHOICES = [
        ("woocommerce", "WooCommerce"),
        ("mercadolibre", "MercadoLibre"),
        ("shopify", "Shopify"),
        ("tiendanube", "Tiendanube"),
        ("manual", "Venta Manual / B2B"),
        ("pos", "Punto de Venta"),
    ]

    empresa = models.ForeignKey(ConfiguracionEmpresa, on_delete=models.CASCADE, related_name="canales_venta")
    nombre = models.CharField(max_length=100, unique=True, help_text="Ej: Tienda Oficial B2C")
    codigo = models.CharField(max_length=20, unique=True, help_text="Ej: WC-B2C, ML-OFICIAL, POS-01")
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default="manual")
    almacen_predeterminado = models.ForeignKey(
        Ubicacion,
        on_delete=models.RESTRICT,
        help_text="Ubicación física de stock de donde se reserva/despacha este canal",
        null=True,
        blank=True,
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Canal de Venta"
        verbose_name_plural = "Canales de Venta"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class OrdenVenta(DocumentoBase):
    """
    Representa un Pedido de Venta (B2C o B2B).
    Genera remitos de salida y facturas de venta.
    Completamente agnóstico del canal de captura externo.
    """
    SECUENCIA_CODIGO = "ventas.ov"

    ESTADO_CHOICES = [
        ("presupuesto", "Presupuesto / Cotización"),
        ("nota_pedido", "Nota de Pedido (Borrador)"),
        ("confirmado", "Orden Confirmada"),
        ("finalizado", "Finalizado (Entregado y Facturado)"),
        ("cancelado", "Cancelado"),
        ("anulado", "Anulado"),
    ]

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default="presupuesto",
        verbose_name="Estado",
    )
    fecha_validez = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de Validez del Presupuesto",
        help_text="Fecha límite de vigencia de las condiciones y precios cotizados.",
    )

    canal = models.ForeignKey(
        CanalVenta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes",
    )
    # Referencia genérica al identificador de la orden en el canal externo
    referencia_externa = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Identificador único en el sistema externo (ID de orden en Woo, MeLi, etc.)",
    )
    numero_externo = models.CharField(
        max_length=100,
        blank=True,
        help_text="Número legible de comprobante o pedido en el canal externo",
    )
    estado_canal_externo = models.CharField(
        max_length=50,
        blank=True,
        help_text="Estado original en el canal externo (ej. processing, completed, paid)",
    )

    cliente = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        related_name="ordenes_venta",
    )
    lista_precio = models.ForeignKey(
        ListaPrecio,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="ordenes_venta",
        verbose_name=_("Lista de Precios"),
        help_text=_("Lista de precios aplicada a este pedido/presupuesto"),
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
    cupones_aplicados = models.JSONField(default=list, blank=True)  # [{code, discount}]

    # Metadatos flexibles no mapeados a columnas
    datos_adicionales_meta = models.JSONField(default=dict, blank=True)

    # Propiedades de compatibilidad regresiva controlada
    @property
    def tienda(self):
        """Compatibilidad con código previo que consultaba orden.tienda."""
        if hasattr(self.canal, "config_woocommerce"):
            return self.canal.config_woocommerce
        return self.canal

    @property
    def wc_order_id(self):
        return int(self.referencia_externa) if self.referencia_externa and self.referencia_externa.isdigit() else self.referencia_externa

    @property
    def wc_order_number(self):
        return self.numero_externo

    @property
    def wc_status(self):
        return self.estado_canal_externo

    class Meta:
        verbose_name = "Orden de Venta"
        verbose_name_plural = "Órdenes de Venta"
        unique_together = [("canal", "referencia_externa")]


class LineaOrdenVenta(models.Model):
    orden = models.ForeignKey(OrdenVenta, on_delete=models.CASCADE, related_name="lineas")
    producto = models.ForeignKey(Producto, on_delete=models.RESTRICT)
    referencia_linea_externa = models.CharField(max_length=100, null=True, blank=True)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=15, decimal_places=2)
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    descuento = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    total_linea = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)

    @property
    def wc_line_id(self):
        return int(self.referencia_linea_externa) if self.referencia_linea_externa and self.referencia_linea_externa.isdigit() else self.referencia_linea_externa

    def save(self, *args, **kwargs):
        self.subtotal = self.cantidad * self.precio_unitario
        self.total_linea = self.subtotal - self.descuento
        super().save(*args, **kwargs)


class LineaRecargoOrden(models.Model):
    """Mapeo de recargos de pasarelas (MercadoPago, intereses) o servicios extra."""
    orden = models.ForeignKey(OrdenVenta, on_delete=models.CASCADE, related_name="recargos")
    nombre = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=15, decimal_places=2)
    impuesto = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
