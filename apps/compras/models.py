from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.base.models import DocumentoBase, TimeStampedModel

class TarifaProveedor(TimeStampedModel):
    """
    Lista de precios de proveedor (Odoo: product.supplierinfo).
    Permite automatizar compras y reabastecimiento conociendo quién vende qué, a qué precio y cuánto tarda.
    """
    proveedor = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.CASCADE,
        limit_choices_to=models.Q(tipo__in=["proveedor", "cliente_proveedor"]),
        verbose_name=_("Proveedor"),
    )
    producto = models.ForeignKey(
        "inventario.Producto",
        on_delete=models.CASCADE,
        related_name="tarifas_proveedores",
        verbose_name=_("Insumo / Producto (SKU)"),
    )
    moneda = models.ForeignKey(
        "base.Moneda",
        on_delete=models.RESTRICT,
        verbose_name=_("Moneda"),
    )
    precio = models.DecimalField(max_digits=15, decimal_places=4, verbose_name=_("Precio Unitario"))
    cantidad_minima = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("1.0000"), verbose_name=_("Cantidad Mínima Requerida"))
    tiempo_entrega_dias = models.PositiveIntegerField(default=1, verbose_name=_("Tiempo de Entrega (Días)"), help_text=_("Lead time desde que se pide hasta que llega"))
    vigencia_desde = models.DateField(null=True, blank=True, verbose_name=_("Vigencia Desde"))
    vigencia_hasta = models.DateField(null=True, blank=True, verbose_name=_("Vigencia Hasta"))

    class Meta:
        verbose_name = _("Tarifa de Proveedor")
        verbose_name_plural = _("Tarifas de Proveedores")
        ordering = ["producto", "precio"]

    def __str__(self):
        return f"{self.proveedor.nombre} - {self.producto.sku} ({self.moneda.simbolo} {self.precio})"
class OrdenCompra(DocumentoBase):
    """
    Orden de Compra comercial a proveedores de insumos o servicios (Odoo: purchase.order).
    Hereda de DocumentoBase: numero, fecha, estado, observaciones, creado_en, modificado_en, adjuntos.
    Ciclo de vida: borrador -> confirmado -> finalizado (o cancelado/anulado).
    """

    proveedor = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        related_name="ordenes_compra",
        limit_choices_to=models.Q(tipo__in=["proveedor", "cliente_proveedor"]),
        verbose_name=_("Proveedor"),
    )
    fecha_entrega_esperada = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Fecha de entrega esperada"),
    )
    condicion_pago = models.ForeignKey(
        "contabilidad.CondicionPago",
        on_delete=models.RESTRICT,
        verbose_name=_("Condición de pago"),
    )
    moneda = models.ForeignKey(
        "base.Moneda",
        on_delete=models.RESTRICT,
        verbose_name=_("Moneda"),
    )
    tipo_cambio = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("1.0000"),
        verbose_name=_("Tipo de cambio"),
        help_text=_("Cotización respecto a ARS al momento de emitir la orden"),
    )
    origen_op = models.ForeignKey(
        "produccion.OrdenProduccion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra",
        verbose_name=_("Orden de Producción origen"),
        help_text=_("OP que originó esta necesidad de compra de insumos"),
    )

    class Meta(DocumentoBase.Meta):
        verbose_name = _("Orden de compra")
        verbose_name_plural = _("Órdenes de compra")

    def __str__(self):
        return f"{self.numero} - {self.proveedor.nombre} [{self.get_estado_display()}]"

    @property
    def subtotal(self):
        return sum((linea.subtotal for linea in self.lineas.all()), Decimal("0.00"))

    @property
    def total_iva(self):
        return sum((linea.iva_monto for linea in self.lineas.all()), Decimal("0.00"))

    @property
    def total(self):
        return self.subtotal + self.total_iva

    @property
    def cantidad_total_pedida(self):
        return sum((linea.cantidad for linea in self.lineas.all()), Decimal("0.00"))

    @property
    def cantidad_total_recibida(self):
        return sum((linea.cantidad_recibida for linea in self.lineas.all()), Decimal("0.00"))

    @property
    def porcentaje_recibido(self):
        pedida = self.cantidad_total_pedida
        if pedida > 0:
            return round((self.cantidad_total_recibida / pedida) * 100, 2)
        return Decimal("0.00")

    @property
    def estado_recepcion(self):
        """Calcula dinámicamente si el abastecimiento está pendiente, parcial o completo."""
        lineas = list(self.lineas.all())
        if not lineas:
            return "sin_lineas"
        recibidas = sum(l.cantidad_recibida for l in lineas)
        pedidas = sum(l.cantidad for l in lineas)
        if recibidas <= Decimal("0.0"):
            return "pendiente"
        elif recibidas < pedidas:
            return "parcial"
        else:
            return "completo"

    @property
    def estado_facturacion(self):
        """Calcula si la facturación del proveedor está pendiente, parcial o completa."""
        lineas = list(self.lineas.all())
        if not lineas:
            return "sin_lineas"
        facturadas = sum(l.cantidad_facturada for l in lineas)
        pedidas = sum(l.cantidad for l in lineas)
        if facturadas <= Decimal("0.0"):
            return "pendiente"
        elif facturadas < pedidas:
            return "parcial"
        else:
            return "completo"

    def get_movimientos_stock(self):
        """Devuelve todos los movimientos de stock asociados a esta orden de compra."""
        from apps.inventario.models import MovimientoStock
        return MovimientoStock.objects.filter(
            models.Q(documento_origen=self.numero) | models.Q(numero__startswith=f"REC-{self.numero}")
        ).distinct()

    def generar_recepcion_stock(self, almacen_destino=None, usuario=None):
        """
        Crea o retorna el MovimientoStock entrante (Remito de recepción) en Almacén.
        """
        from apps.inventario.models import Ubicacion, MovimientoStock, LineaMovimientoStock

        if not almacen_destino:
            almacen_destino, _ = Ubicacion.objects.get_or_create(
                tipo="interna", defaults={"nombre": "Almacén Principal", "activa": True}
            )

        virtual_proveedor, _ = Ubicacion.objects.get_or_create(
            tipo="proveedor", defaults={"nombre": "Proveedores (Virtual)", "activa": True}
        )

        numero_rec = f"REC-{self.numero}"
        movimiento, created = MovimientoStock.objects.get_or_create(
            numero=numero_rec,
            defaults={
                "tipo": "recepcion",
                "estado": "confirmado",
                "contacto": self.proveedor,
                "ubicacion_origen": virtual_proveedor,
                "ubicacion_destino": almacen_destino,
                "documento_origen": self.numero,
                "responsable": usuario,
                "observaciones": f"Recepción de mercadería para Orden de Compra {self.numero}",
            },
        )

        if created:
            for linea in self.lineas.all():
                LineaMovimientoStock.objects.create(
                    movimiento=movimiento,
                    producto=linea.producto,
                    cantidad=linea.cantidad,
                    cantidad_hecha=Decimal("0.0"),
                    ubicacion_origen=virtual_proveedor,
                    ubicacion_destino=almacen_destino,
                    estado="borrador",
                    referencia=f"OC {self.numero} - {linea.producto.sku}",
                )

        return movimiento

    def actualizar_cantidades_recibidas(self):
        """
        Sincroniza las cantidades recibidas sumando los remitos entrantes finalizados
        (incluyendo remitos iniciales y sus backorders generados por recepciones parciales).
        Si todas las cantidades fueron recibidas y la orden estaba confirmada, pasa a finalizado.
        """
        from apps.inventario.models import LineaMovimientoStock

        for linea in self.lineas.all():
            total_recibido = (
                LineaMovimientoStock.objects.filter(
                    movimiento__tipo="recepcion",
                    movimiento__estado="finalizado",
                    movimiento__documento_origen=self.numero,
                    producto=linea.producto,
                    estado="realizado",
                ).aggregate(total=models.Sum("cantidad_hecha"))["total"]
                or Decimal("0.0000")
            )
            linea.cantidad_recibida = total_recibido
            linea.save(update_fields=["cantidad_recibida"])

        if self.estado == "confirmado" and self.estado_recepcion == "completo":
            self.estado = "finalizado"
            self.save(update_fields=["estado"])


class LineaOrdenCompra(TimeStampedModel):
    """
    Línea de detalle en la Orden de Compra (Odoo: purchase.order.line).
    Especifica SKU, cantidad, unidad de medida, precio pactado y seguimiento de recepción.
    """

    orden_compra = models.ForeignKey(
        OrdenCompra,
        on_delete=models.CASCADE,
        related_name="lineas",
        verbose_name=_("Orden de compra"),
    )
    producto = models.ForeignKey(
        "inventario.Producto",
        on_delete=models.RESTRICT,
        related_name="lineas_orden_compra",
        verbose_name=_("Producto / Insumo (SKU)"),
    )
    descripcion = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Descripción adicional"),
    )
    unidad_medida = models.ForeignKey(
        "inventario.UnidadMedida",
        on_delete=models.RESTRICT,
        related_name="lineas_compra",
        verbose_name=_("Unidad de medida"),
    )
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name=_("Cantidad pedida"),
    )
    cantidad_recibida = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0000"),
        verbose_name=_("Cantidad recibida"),
    )
    cantidad_facturada = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0000"),
        verbose_name=_("Cantidad facturada"),
    )
    precio_unitario = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        default=Decimal("0.0000"),
        verbose_name=_("Precio unitario"),
    )
    impuesto = models.ForeignKey(
        "contabilidad.Impuesto",
        on_delete=models.RESTRICT,
        verbose_name=_("Impuesto"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Línea de orden de compra")
        verbose_name_plural = _("Líneas de orden de compra")
        ordering = ["id"]

    def __str__(self):
        return f"{self.cantidad} x {self.producto} ({self.orden_compra.numero})"

    @property
    def cantidad_pendiente(self):
        return max(Decimal("0.0"), self.cantidad - self.cantidad_recibida)

    @property
    def subtotal(self):
        return round(self.cantidad * self.precio_unitario, 2)

    @property
    def iva_monto(self):
        if self.impuesto:
            return round(self.subtotal * (self.impuesto.alicuota / Decimal("100.0")), 2)
        return Decimal("0.00")

    @property
    def total(self):
        return self.subtotal + self.iva_monto

    def save(self, *args, **kwargs):
        # Auto-completar unidad de medida desde el template del producto si no fue especificada
        if not self.unidad_medida_id and self.producto_id:
            self.unidad_medida = self.producto.template.unidad_medida
        super().save(*args, **kwargs)
