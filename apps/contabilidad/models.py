from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
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
    cuenta_imputacion = models.ForeignKey(
        "Cuenta",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        verbose_name="Cuenta Contable",
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
        ("deuda_fdi", "Obligación Negociable (Crédito FDI)"),
        ("deuda_fiscal", "Deuda Fiscal / DDJJ (No Comercial)"),
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

        with transaction.atomic():
            # Bloquear la fila de DocumentoDeuda para que no entren pagos concurrentes
            doc = DocumentoDeuda.objects.select_for_update().get(
                pk=self.documento_deuda_id
            )

            # Solo validamos si es creación (no tiene PK)
            if not self.pk:
                saldo = doc.saldo_pendiente
                if self.monto_aplicado > saldo:
                    raise ValidationError(
                        f"Monto a aplicar ({self.monto_aplicado}) supera el saldo pendiente de la deuda ({saldo})."
                    )

            super().save(*args, **kwargs)
            doc.actualizar_estado_pago()

    def delete(self, *args, **kwargs):
        from django.db import transaction

        with transaction.atomic():
            doc = DocumentoDeuda.objects.select_for_update().get(
                pk=self.documento_deuda_id
            )
            super().delete(*args, **kwargs)
            doc.actualizar_estado_pago()


# ==============================================================================
# NÚCLEO CONTABLE (PARTIDA DOBLE ESTRICTA)
# ==============================================================================


class Cuenta(TimeStampedModel):
    """
    Plan de Cuentas Jerárquico.
    """

    TIPO_CHOICES = [
        ("activo", "Activo"),
        ("pasivo", "Pasivo"),
        ("patrimonio", "Patrimonio Neto"),
        ("resultado_positivo", "Resultado Positivo (Ingresos)"),
        ("resultado_negativo", "Resultado Negativo (Gastos)"),
    ]
    NATURAL_CHOICES = [
        ("deudora", "Deudora (Suma al Debe)"),
        ("acreedora", "Acreedora (Suma al Haber)"),
    ]

    codigo = models.CharField(
        max_length=20, unique=True, verbose_name="Código (Ej: 1.1.01)"
    )
    nombre = models.CharField(max_length=150, verbose_name="Nombre de la Cuenta")
    padre = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subcuentas",
    )

    tipo = models.CharField(
        max_length=20, choices=TIPO_CHOICES, verbose_name="Clasificación"
    )
    naturaleza = models.CharField(
        max_length=15, choices=NATURAL_CHOICES, verbose_name="Naturaleza del Saldo"
    )
    imputable = models.BooleanField(
        default=True,
        verbose_name="¿Es imputable?",
        help_text="Falso si es una cuenta agrupadora (Ej: 'Activo'). Solo las hojas reciben asientos.",
    )

    class Meta:
        verbose_name = "Cuenta Contable"
        verbose_name_plural = "Cuentas Contables (Plan)"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class Asiento(TimeStampedModel):
    """
    Cabecera de un movimiento en el Libro Diario.
    """

    ESTADO_CHOICES = [
        ("borrador", "Borrador (Descuadrado o Pendiente)"),
        ("asentado", "Asentado (Cuadrado e Inmutable)"),
        ("anulado", "Anulado (Revertido)"),
    ]

    numero = models.CharField(max_length=50, unique=True, verbose_name="N° de Asiento")
    fecha = models.DateField(verbose_name="Fecha Contable")
    descripcion = models.CharField(max_length=255, verbose_name="Concepto / Leyenda")

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="borrador")

    diario = models.ForeignKey(
        Diario, on_delete=models.RESTRICT, related_name="asientos"
    )

    # Enlace Universal Genérico (Relaciona el asiento con OP, Factura, Recibo, Liquidación Nomina)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    documento_origen = GenericForeignKey("content_type", "object_id")

    class Meta:
        verbose_name = "Asiento Contable"
        verbose_name_plural = "Libro Diario (Asientos)"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Asiento {self.numero} - {self.fecha} ({self.get_estado_display()})"


class Apunte(models.Model):
    """
    Línea individual de un asiento contable.
    Representa el movimiento monetario al Debe o al Haber de una cuenta.
    """

    asiento = models.ForeignKey(
        Asiento, on_delete=models.CASCADE, related_name="apuntes"
    )
    cuenta = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, related_name="apuntes"
    )

    debe = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    haber = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    # Rastreabilidad auxiliar
    contacto = models.ForeignKey(
        "contactos.Contacto", on_delete=models.SET_NULL, null=True, blank=True
    )
    descripcion_linea = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Apunte Contable"
        verbose_name_plural = "Apuntes Contables (Líneas)"


# ==============================================================================
# GOBERNANZA FISCAL Y TRIBUTACIÓN (ARCA/ARBA)
# ==============================================================================


class FacturaImpuesto(TimeStampedModel):
    """
    Percepciones o recargos impositivos aplicados al momento de FACTURAR.
    Ejemplo: Percepción de IIBB o IVA Adicional en una Factura de Venta.
    """

    documento = models.ForeignKey(
        "contabilidad.DocumentoDeuda",
        on_delete=models.CASCADE,
        related_name="impuestos_aplicados",
    )
    impuesto = models.ForeignKey(Impuesto, on_delete=models.RESTRICT)

    base_imponible = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    monto_impuesto = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    liquidado = models.BooleanField(
        default=False, help_text="¿Fue incluido en una DDJJ?"
    )

    class Meta:
        verbose_name = "Impuesto de Factura"
        verbose_name_plural = "Impuestos de Factura"

    def __str__(self):
        return f"{self.impuesto.nombre} s/ {self.documento.numero}"


class CertificadoRetencion(TimeStampedModel):
    """
    Retenciones practicadas o sufridas al momento de PAGAR o COBRAR.
    Ejemplo: Retención de Ganancias a un Tallerista, o que un Cliente nos retenga a nosotros.
    Va atado al comprobante de Tesorería.
    """

    TIPO_RETENCION_CHOICES = [
        ("emitida", "Emitida (Retenemos a un Proveedor)"),
        ("sufrida", "Sufrida (Nos retiene un Cliente)"),
    ]

    comprobante_pago = models.ForeignKey(
        "tesoreria.ComprobanteTesoreria",
        on_delete=models.CASCADE,
        related_name="retenciones",
    )
    impuesto = models.ForeignKey(Impuesto, on_delete=models.RESTRICT)

    tipo = models.CharField(max_length=20, choices=TIPO_RETENCION_CHOICES)
    numero_certificado = models.CharField(
        max_length=50, blank=True, verbose_name="N° Certificado"
    )

    base_imponible = models.DecimalField(max_digits=15, decimal_places=2)
    monto_retenido = models.DecimalField(max_digits=15, decimal_places=2)

    fecha_retencion = models.DateField()
    liquidado = models.BooleanField(
        default=False, help_text="¿Fue depositado en ARCA vía SICORE?"
    )

    class Meta:
        verbose_name = "Certificado de Retención"
        verbose_name_plural = "Certificados de Retención"

    def __str__(self):
        return f"Retención {self.impuesto.nombre} - {self.monto_retenido}"


class LiquidacionImpuesto(TimeStampedModel):
    """
    Cabecera de Declaración Jurada Mensual (Ej. SICORE, SIFERE, F2002 IVA).
    Agrupa percepciones y retenciones para pagarle al Fisco.
    """

    ESTADO_CHOICES = [
        ("borrador", "Borrador (Cálculo)"),
        ("presentada", "Presentada (Genera VEP / Deuda)"),
        ("pagada", "Pagada (VEP Cancelado)"),
    ]

    nombre = models.CharField(
        max_length=100, help_text="Ej: SICORE - Retenciones Ganancias Jun/2026"
    )
    periodo_mes = models.PositiveIntegerField()
    periodo_anio = models.PositiveIntegerField()

    impuesto = models.ForeignKey(
        Impuesto,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        help_text="Obligatorio si es DDJJ específica",
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="borrador")

    saldo_a_pagar = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    # Cuando se presenta, se genera un DocumentoDeuda (Factura Proveedor a favor de AFIP)
    deuda_generada = models.ForeignKey(
        "contabilidad.DocumentoDeuda", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "Liquidación de Impuesto (DDJJ)"
        verbose_name_plural = "Liquidaciones de Impuestos (DDJJ)"

    def __str__(self):
        return f"{self.nombre} ({self.get_estado_display()})"


class LiquidacionDetalle(models.Model):
    """
    Tabla intermedia que marca exactamente qué FacturasImpuesto o CertificadosRetencion
    fueron declarados en esta Liquidación Mensual, evitando que se declaren dos veces.
    """

    liquidacion = models.ForeignKey(
        LiquidacionImpuesto, on_delete=models.CASCADE, related_name="detalles"
    )

    factura_impuesto = models.ForeignKey(
        FacturaImpuesto, on_delete=models.SET_NULL, null=True, blank=True
    )
    certificado_retencion = models.ForeignKey(
        CertificadoRetencion, on_delete=models.SET_NULL, null=True, blank=True
    )

    monto_computado = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        verbose_name = "Detalle de Liquidación"
        verbose_name_plural = "Detalles de Liquidación"


# ==============================================================================
# PERFILES CONTABLES (EXTENSIONES ONETOONE PARA MODO HEADLESS)
# ==============================================================================


class ConfiguracionContable(TimeStampedModel):
    """Fallback Global (Extiende ConfiguracionEmpresa)"""

    empresa = models.OneToOneField(
        "base.ConfiguracionEmpresa",
        on_delete=models.CASCADE,
        related_name="contabilidad",
    )
    cuenta_clientes_defecto = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, related_name="+"
    )
    cuenta_proveedores_defecto = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, related_name="+"
    )
    cuenta_ventas_defecto = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, related_name="+"
    )
    cuenta_gastos_defecto = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, related_name="+"
    )

    class Meta:
        verbose_name = "Configuración Contable"
        verbose_name_plural = "Configuraciones Contables"


class PerfilContableContacto(TimeStampedModel):
    """Perfil Individual por Contacto (Extiende Contacto)"""

    contacto = models.OneToOneField(
        "contactos.Contacto", on_delete=models.CASCADE, related_name="perfil_contable"
    )
    cuenta_a_cobrar = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    cuenta_a_pagar = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Perfil Contable de Contacto"
        verbose_name_plural = "Perfiles Contables de Contactos"


class PerfilContableProducto(TimeStampedModel):
    """Perfil Individual por Producto (Extiende Producto)"""

    METODO_VALUACION_CHOICES = [
        ("fifo", "P.E.P.S. (FIFO)"),
        ("promedio", "Promedio Ponderado"),
        ("especifica", "Identificación Específica"),
    ]

    producto = models.OneToOneField(
        "inventario.Producto", on_delete=models.CASCADE, related_name="perfil_contable"
    )

    metodo_valuacion = models.CharField(
        max_length=20,
        choices=METODO_VALUACION_CHOICES,
        default="promedio",
        verbose_name="Método de Valuación",
        help_text="Método de costeo para las salidas de inventario.",
    )

    # Comercial
    cuenta_ingreso = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    cuenta_gasto = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )

    # Inventario y Producción (Valuación Anglo-Sajona)
    cuenta_valuacion_stock = models.ForeignKey(
        Cuenta,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Ej: Materias Primas / Productos Terminados",
    )
    cuenta_entrada_stock = models.ForeignKey(
        Cuenta,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Ej: Puente Facturas a Recibir",
    )
    cuenta_salida_stock = models.ForeignKey(
        Cuenta,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Ej: CMV - Costo de Mercaderías Vendidas",
    )
    cuenta_produccion_proceso = models.ForeignKey(
        Cuenta,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Ej: WIP - Trabajo en Proceso",
    )

    class Meta:
        verbose_name = "Perfil Contable de Producto"
        verbose_name_plural = "Perfiles Contables de Productos"


class PerfilContableUbicacion(TimeStampedModel):
    """
    Perfil Contable para Ubicaciones (Extiende Ubicación de Inventario).
    Ideal para ubicaciones virtuales como 'Pérdidas de Inventario' o 'Scrap (Desechos)'.
    """

    ubicacion = models.OneToOneField(
        "inventario.Ubicacion", on_delete=models.CASCADE, related_name="perfil_contable"
    )
    cuenta_valuacion_ubicacion = models.ForeignKey(
        Cuenta,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Cuenta de contrapartida (Ej: Cuenta de Gasto por Mermas o Scrap)",
    )

    class Meta:
        verbose_name = "Perfil Contable de Ubicación"
        verbose_name_plural = "Perfiles Contables de Ubicaciones"


# ==============================================================================
# ACTIVOS FIJOS (BIENES DE USO) Y DEPRECIACIONES
# ==============================================================================


class ActivoFijo(TimeStampedModel):
    """
    Modelo para gestionar Bienes de Uso y su amortización (depreciación).
    """

    METODO_DEPRECIACION_CHOICES = [
        ("lineal", "Lineal (Meses/Años)"),
        ("unidades", "Por Unidades de Producción"),
    ]

    nombre = models.CharField(max_length=150, verbose_name="Nombre del Activo")
    fecha_adquisicion = models.DateField(verbose_name="Fecha de Adquisición")
    valor_original = models.DecimalField(
        max_digits=15, decimal_places=2, verbose_name="Valor de Adquisición"
    )
    valor_residual_estimado = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0.00,
        verbose_name="Valor Residual (Descarte)",
    )

    metodo_depreciacion = models.CharField(
        max_length=20, choices=METODO_DEPRECIACION_CHOICES, default="lineal"
    )
    vida_util_meses = models.PositiveIntegerField(
        default=60, help_text="Ej: 60 meses para Muebles, 120 para Maquinaria"
    )

    # Cuentas Contables
    cuenta_activo = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, related_name="+"
    )
    cuenta_depreciacion_acumulada = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, related_name="+"
    )
    cuenta_gasto_depreciacion = models.ForeignKey(
        Cuenta, on_delete=models.RESTRICT, related_name="+"
    )

    # Factura asociada (si existe)
    documento_origen = models.ForeignKey(
        "contabilidad.DocumentoDeuda", on_delete=models.SET_NULL, null=True, blank=True
    )

    estado = models.CharField(
        max_length=20,
        choices=[
            ("borrador", "Borrador"),
            ("activo", "Activo"),
            ("vendido", "Vendido/Descartado"),
        ],
        default="borrador",
    )

    class Meta:
        verbose_name = "Activo Fijo (Bien de Uso)"
        verbose_name_plural = "Activos Fijos"

    def __str__(self):
        return f"{self.nombre} (Adq: {self.fecha_adquisicion})"


class TablaDepreciacion(TimeStampedModel):
    """
    Líneas proyectadas y ejecutadas de la amortización de un Activo Fijo.
    """

    activo_fijo = models.ForeignKey(
        ActivoFijo, on_delete=models.CASCADE, related_name="tabla_depreciaciones"
    )
    fecha_ejecucion = models.DateField(verbose_name="Fecha de Amortización")
    monto = models.DecimalField(
        max_digits=15, decimal_places=2, verbose_name="Monto Amortizado"
    )

    estado = models.CharField(
        max_length=20,
        choices=[("proyectado", "Proyectado"), ("asentado", "Asentado Contablemente")],
        default="proyectado",
    )
    asiento = models.ForeignKey(
        "contabilidad.Asiento", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "Línea de Depreciación"
        verbose_name_plural = "Tabla de Depreciaciones"
        ordering = ["fecha_ejecucion"]
