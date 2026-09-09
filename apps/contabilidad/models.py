from django.db import models
from apps.base.models import TimeStampedModel


class CondicionPago(TimeStampedModel):
    """
    Modelo para condiciones de pago (Odoo: account.payment.term).
    Define el plazo y estructuración financiera de una deuda (ej. 30/60 días).
    """

    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")
    activa = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Condición de pago"
        verbose_name_plural = "Condiciones de pago"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class LineaCondicionPago(models.Model):
    """
    Línea de condición de pago (Odoo: account.payment.term.line).
    Permite desglosar un pago en múltiples cuotas o vencimientos.
    """

    TIPO_VALOR_CHOICES = [
        ("porcentaje", "Porcentaje"),
        ("monto_fijo", "Monto Fijo"),
        ("saldo", "Saldo Restante"),
    ]

    condicion_pago = models.ForeignKey(
        CondicionPago, on_delete=models.CASCADE, related_name="lineas"
    )
    tipo_valor = models.CharField(
        max_length=20, choices=TIPO_VALOR_CHOICES, default="porcentaje"
    )
    valor = models.DecimalField(
        max_digits=5, decimal_places=2, default=100.00, help_text="Ej. 50 para 50%"
    )
    dias = models.PositiveIntegerField(
        default=0,
        verbose_name="Días de plazo",
        help_text="Días desde la fecha de factura",
    )

    class Meta:
        verbose_name = "Línea de condición de pago"
        verbose_name_plural = "Líneas de condición de pago"
        ordering = ["dias"]


class Impuesto(TimeStampedModel):
    """
    Modelo para tasas de impuestos, retenciones y percepciones (Odoo: account.tax).
    """

    TIPO_IMPUESTO_CHOICES = [
        ("iva", "IVA"),
        ("retencion_iva", "Retención de IVA"),
        ("retencion_iibb", "Retención de IIBB"),
        ("retencion_ganancias", "Retención de Ganancias"),
        ("percepcion_iva", "Percepción de IVA"),
        ("percepcion_iibb", "Percepción de IIBB"),
        ("otro", "Otro"),
    ]

    APLICACION_CHOICES = [
        ("ventas", "Ventas (Clientes)"),
        ("compras", "Compras (Proveedores)"),
        ("ambas", "Ambas"),
    ]

    nombre = models.CharField(max_length=100, verbose_name="Nombre del impuesto")
    tipo = models.CharField(
        max_length=30,
        choices=TIPO_IMPUESTO_CHOICES,
        default="iva",
        verbose_name="Tipo de impuesto",
    )
    aplicacion = models.CharField(
        max_length=20,
        choices=APLICACION_CHOICES,
        default="ambas",
        verbose_name="Aplicación",
    )
    alicuota = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="Alícuota %"
    )
    afip_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="ID AFIP (IVA)",
        help_text="Ej: 5 para 21%, 4 para 10.5%, 6 para 27%",
    )
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Impuesto / Alícuota"
        verbose_name_plural = "Impuestos y Alícuotas"
        ordering = ["tipo", "alicuota"]

    def __str__(self):
        return f"{self.nombre} ({self.alicuota}%)"


class Diario(TimeStampedModel):
    """
    Diario Contable (Odoo: account.journal).
    Define los puntos de venta de AFIP para la facturación, o secuencias internas.
    """

    TIPO_CHOICES = [
        ("ventas", "Ventas (Facturación a Clientes)"),
        ("compras", "Compras (Facturas de Proveedores)"),
        ("fason", "Liquidaciones de Fasón / Talleristas"),
        ("varios", "Operaciones Varias"),
    ]

    nombre = models.CharField(
        max_length=100, verbose_name="Nombre del Diario (Ej. Ventas Web)"
    )
    codigo = models.CharField(
        max_length=10, unique=True, verbose_name="Código Corto (Ej. VEN1)"
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="ventas")

    # AFIP
    punto_venta_afip = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Punto de Venta AFIP",
        help_text="Ej. 1, 2, 3. Obligatorio si se emiten comprobantes electrónicos.",
    )
    es_exportacion = models.BooleanField(
        default=False,
        verbose_name="¿Usa WSFEX (Exportación)?",
        help_text="Marcar si este punto de venta está habilitado en AFIP para Facturas E.",
    )

    class Meta:
        verbose_name = "Diario / Punto de Venta"
        verbose_name_plural = "Diarios / Puntos de Venta"
        ordering = ["tipo", "codigo"]

    def __str__(self):
        return (
            f"[{self.codigo}] {self.nombre} (PV: {self.punto_venta_afip or 'Interno'})"
        )


class TipoComprobanteAFIP(models.Model):
    """
    Tabla oficial de códigos de comprobantes según AFIP.
    Inspirado en l10n_latam.document.type de Odoo y django-afip.
    """

    CLASIFICACION_CHOICES = (
        ("factura", "Factura"),
        ("nota_debito", "Nota de Débito"),
        ("nota_credito", "Nota de Crédito"),
        ("recibo", "Recibo"),
        ("remito", "Remito / Otros"),
    )

    codigo = models.CharField(
        max_length=3,
        unique=True,
        primary_key=True,
        verbose_name="Código AFIP (3 dígitos)",
    )
    nombre = models.CharField(
        max_length=150, verbose_name="Nombre Oficial (Ej. Factura A)"
    )
    letra = models.CharField(max_length=1, verbose_name="Letra (A, B, C, E, M, R, X)")
    clasificacion_interna = models.CharField(
        max_length=20, choices=CLASIFICACION_CHOICES
    )

    es_electronico = models.BooleanField(
        default=True, help_text="¿Requiere solicitar CAE por WSFE?"
    )
    es_mipyme_fce = models.BooleanField(
        default=False, help_text="¿Es Factura de Crédito Electrónica (FCE)?"
    )
    es_exportacion = models.BooleanField(
        default=False, help_text="¿Utiliza WSFEX (Exportación)?"
    )

    class Meta:
        verbose_name = "Tipo de Comprobante AFIP"
        verbose_name_plural = "Tipos de Comprobantes AFIP"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class DocumentoDeuda(TimeStampedModel):
    """
    Representa una Factura, Nota de Débito, Nota de Crédito o Liquidación de Fasón.
    Es el origen del devengado (Cuenta Corriente). (Odoo: account.move).
    """

    TIPO_CHOICES = [
        ("factura_cliente", "Factura de Venta (Cliente)"),
        ("factura_proveedor", "Factura de Compra (Proveedor)"),
        ("nota_debito_cliente", "Nota de Débito (Cliente)"),
        ("nota_credito_cliente", "Nota de Crédito (Cliente)"),
        ("nota_debito_proveedor", "Nota de Débito (Proveedor)"),
        ("nota_credito_proveedor", "Nota de Crédito (Proveedor)"),
        ("liquidacion_fason", "Liquidación de Servicio (Fasón / Tallerista)"),
    ]

    ESTADO_CHOICES = [
        ("borrador", "Borrador"),
        ("publicado", "Publicado / Emitido"),
        ("pagado_parcial", "Pagado Parcialmente"),
        ("pagado", "Pagado (Conciliado)"),
        ("cancelado", "Cancelado"),
    ]

    numero = models.CharField(
        max_length=50, unique=True, verbose_name="Número de Comprobante"
    )

    # Diario / Punto de Venta al que pertenece
    diario = models.ForeignKey(
        Diario,
        on_delete=models.RESTRICT,
        related_name="documentos",
        verbose_name="Diario / Punto de Venta",
    )

    # Orientación interna (Ej. Factura de Venta, Nota de Crédito de Compra)
    tipo = models.CharField(
        max_length=30, choices=TIPO_CHOICES, verbose_name="Orientación del Documento"
    )

    # Estandarización Fiscal
    tipo_comprobante_afip = models.ForeignKey(
        TipoComprobanteAFIP,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        verbose_name="Tipo AFIP",
        help_text="Dejar en blanco para comprobantes internos (X)",
    )

    contacto = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        related_name="documentos_deuda",
        verbose_name="Cliente / Proveedor / Tallerista",
    )

    fecha_emision = models.DateField(verbose_name="Fecha de Emisión")
    fecha_vencimiento = models.DateField(
        blank=True, null=True, verbose_name="Fecha de Vencimiento"
    )
    condicion_pago = models.ForeignKey(
        CondicionPago, on_delete=models.SET_NULL, null=True, blank=True
    )

    moneda = models.ForeignKey(
        "base.Moneda", on_delete=models.RESTRICT, null=True, verbose_name="Moneda"
    )
    tasa_cambio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=1.0,
        verbose_name="Cotización (AFIP)",
        help_text="1.0 para Pesos, valor oficial para Dólares.",
    )

    monto_neto = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, verbose_name="Monto Neto"
    )
    monto_impuestos = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, verbose_name="Monto Impuestos"
    )
    monto_total = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, verbose_name="Monto Total"
    )

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="borrador")

    # Datos de validación electrónica (AFIP)
    afip_cae = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="CAE (AFIP)"
    )
    afip_vencimiento_cae = models.DateField(
        blank=True, null=True, verbose_name="Vto. CAE"
    )

    # FK opcional para enlazar automáticamente la liquidación con la OP interna que la originó
    orden_produccion = models.ForeignKey(
        "produccion.OrdenProduccion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facturas",
        verbose_name="Orden de Producción Origen",
    )

    class Meta:
        verbose_name = "Documento de Deuda (Factura)"
        verbose_name_plural = "Documentos de Deuda (Facturas)"
        ordering = ["-fecha_emision", "-id"]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.numero} - {self.contacto.nombre} (${self.monto_total})"

    @property
    def saldo_pendiente(self):
        """Calcula el saldo restando los pagos aplicados al monto total."""
        from django.db.models import Sum
        from decimal import Decimal

        aplicado = self.aplicaciones_recibidas.aggregate(total=Sum("monto_aplicado"))[
            "total"
        ]
        if aplicado is None:
            aplicado = Decimal("0.00")

        return self.monto_total - aplicado

    def actualizar_estado_pago(self):
        """Actualiza el estado de la deuda basado en el saldo pendiente."""
        from decimal import Decimal

        saldo = self.saldo_pendiente
        if saldo <= Decimal("0.00"):
            self.estado = "pagado"
        elif saldo < self.monto_total:
            self.estado = "pagado_parcial"
        elif self.estado in ["pagado", "pagado_parcial"]:
            self.estado = "publicado"
        self.save(update_fields=["estado"])


class LineaDocumentoDeuda(models.Model):
    """
    Línea individual de la factura (Odoo: account.move.line).
    """

    documento = models.ForeignKey(
        DocumentoDeuda, on_delete=models.CASCADE, related_name="lineas"
    )
    producto = models.ForeignKey(
        "inventario.Producto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Producto / Servicio",
    )
    descripcion = models.CharField(max_length=200, verbose_name="Descripción")
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    precio_unitario = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    impuesto = models.ForeignKey(
        Impuesto, on_delete=models.SET_NULL, null=True, blank=True
    )

    subtotal = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Subtotal (Sin Impuestos)",
    )

    class Meta:
        verbose_name = "Línea de Factura"
        verbose_name_plural = "Líneas de Factura"

    def save(self, *args, **kwargs):
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)


class AplicacionPago(TimeStampedModel):
    """
    Motor de Conciliación (Matching).
    Cruza los fondos (Percibido en Tesorería) contra la deuda (Devengado en Contabilidad).
    """

    documento_deuda = models.ForeignKey(
        DocumentoDeuda,
        on_delete=models.CASCADE,
        related_name="aplicaciones_recibidas",
        verbose_name="Factura / Deuda a Cancelar",
    )
    comprobante_pago = models.ForeignKey(
        "tesoreria.ComprobanteTesoreria",
        on_delete=models.CASCADE,
        related_name="aplicaciones_emitidas",
        verbose_name="Recibo / OP de Tesorería",
    )
    monto_aplicado = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Qué porción de los fondos del comprobante se usan para matar esta deuda",
    )
    fecha_aplicacion = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = "Aplicación de Pago (Conciliación)"
        verbose_name_plural = "Aplicaciones de Pago (Conciliaciones)"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.documento_deuda.actualizar_estado_pago()

    def delete(self, *args, **kwargs):
        doc = self.documento_deuda
        super().delete(*args, **kwargs)
        doc.actualizar_estado_pago()
