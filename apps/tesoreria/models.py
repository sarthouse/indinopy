import json
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.db.models import Sum
from apps.base.models import TimeStampedModel, DocumentoBase, DocumentoFirmableMixin


class Caja(TimeStampedModel):
    """
    Representa una caja física, cuenta bancaria o pasarela de pago.
    """

    TIPO_CAJA_CHOICES = [
        ("efectivo", "Caja Efectivo"),
        ("banco", "Cuenta Bancaria"),
        ("tarjeta", "Tarjeta / Pasarela Digital"),
    ]
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Caja / Cuenta")
    tipo = models.CharField(
        max_length=20, choices=TIPO_CAJA_CHOICES, default="efectivo"
    )
    moneda = models.ForeignKey(
        "base.Moneda", on_delete=models.RESTRICT, verbose_name="Moneda"
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Caja / Cuenta"
        verbose_name_plural = "Cajas y Cuentas"
        ordering = ["tipo", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.moneda.codigo})"

    @property
    def saldo_actual(self):
        aggr = self.movimientos.filter(estado="confirmado").aggregate(
            ingresos=Sum("monto_ingreso"), egresos=Sum("monto_egreso")
        )
        ingresos = aggr["ingresos"] or Decimal("0.00")
        egresos = aggr["egresos"] or Decimal("0.00")
        return ingresos - egresos


class ComprobanteTesoreria(DocumentoFirmableMixin, DocumentoBase):
    """
    Documento maestro operativo: Recibo (Cobranza) u Orden de Pago.
    """
    TIPO_COMPROBANTE_CHOICES = [
        ("recibo", "Recibo (Cobranza a Cliente)"),
        ("orden_pago", "Orden de Pago (A Proveedor)"),
        ("transferencia", "Transferencia Interna (Entre cajas)"),
    ]
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_COMPROBANTE_CHOICES,
        verbose_name="Tipo de Operación",
    )

    def save(self, *args, **kwargs):
        if not self.numero:
            self.SECUENCIA_CODIGO = f"tesoreria.{self.tipo}"
        super().save(*args, **kwargs)

    contacto = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        verbose_name="Cliente / Proveedor",
    )
    escrow_asociado = models.ForeignKey(
        "eop.ContratoEOP",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Contrato Escrow asociado",
        help_text="Usado para Fondeo (FDI) o Repago (Marca)",
    )
    referencia_bancaria_vep = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="N° VEP / Ref. Bancaria",
        help_text="Útil para auditoría y conciliación de pagos de impuestos o transferencias agrupadas.",
    )

    class Meta:
        verbose_name = "Comprobante de Tesorería"
        verbose_name_plural = "Comprobantes de Tesorería"

    def __str__(self):
        return f"{self.get_tipo_display()} {self.numero}"

    @property
    def total_ingreso(self):
        return self.valores.aggregate(total=Sum("monto_ingreso"))["total"] or Decimal(
            "0.00"
        )

    @property
    def total_egreso(self):
        return self.valores.aggregate(total=Sum("monto_egreso"))["total"] or Decimal(
            "0.00"
        )

    def generar_payload_canonico(self):
        """
        Genera el payload canónico para firma de la Orden de Pago/Recibo.
        """
        payload = {
            "uuid": str(self.uuid_identificador),
            "numero": self.numero,
            "tipo": self.tipo,
            "fecha": str(self.fecha),
            "contacto_id": self.contacto_id,
            "total_ingreso": str(self.total_ingreso),
            "total_egreso": str(self.total_egreso),
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class MovimientoCaja(TimeStampedModel):
    """
    Línea de valor asociada a un comprobante. Representa la entrada o salida real de valores (Efectivo, Cheques, Retenciones).
    """

    TIPO_VALOR_CHOICES = [
        ("efectivo", "Efectivo"),
        ("transferencia", "Transferencia Bancaria"),
        ("cheque", "Cheque"),
        ("retencion", "Certificado de Retención"),
    ]
    comprobante = models.ForeignKey(
        ComprobanteTesoreria, on_delete=models.CASCADE, related_name="valores"
    )
    caja = models.ForeignKey(
        Caja, on_delete=models.RESTRICT, related_name="movimientos"
    )
    fecha = models.DateField(default=timezone.now)
    tipo_valor = models.CharField(
        max_length=20, choices=TIPO_VALOR_CHOICES, default="efectivo"
    )

    monto_ingreso = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Ingreso"
    )
    monto_egreso = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Egreso"
    )

    # Referencias opcionales
    cheque = models.ForeignKey(
        "Cheque", on_delete=models.SET_NULL, null=True, blank=True
    )
    impuesto = models.ForeignKey(
        "contabilidad.Impuesto",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        help_text="Si es una retención",
    )
    estado = models.CharField(
        max_length=20, choices=DocumentoBase.ESTADO_CHOICES, default="borrador"
    )

    class Meta:
        verbose_name = "Movimiento de Caja"
        verbose_name_plural = "Movimientos de Caja"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.caja.nombre} - {self.get_tipo_valor_display()}"


class Cheque(TimeStampedModel):
    """
    Gestión de Cheques (Terceros y Propios) - Típico en ERPs con localización argentina.
    """

    TIPO_CHEQUE_CHOICES = [
        ("tercero", "Cheque de Terceros"),
        ("propio", "Cheque Propio"),
    ]

    FORMATO_CHOICES = [
        ("fisico", "Físico (Papel)"),
        ("echeq", "E-Cheq (Electrónico)"),
    ]

    CATEGORIA_CHOICES = [
        ("comun", "Común (Al día)"),
        ("diferido", "Pago Diferido (CPD)"),
    ]

    ESTADO_CHOICES = [
        ("en_cartera", "En Cartera"),
        ("entregado", "Entregado a Proveedor"),
        ("depositado", "Depositado en Banco"),
        ("acreditado", "Acreditado / Debitado"),
        ("rechazado", "Rechazado"),
    ]

    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHEQUE_CHOICES,
        default="tercero",
        verbose_name="Origen",
    )
    formato = models.CharField(
        max_length=20, choices=FORMATO_CHOICES, default="fisico", verbose_name="Formato"
    )
    categoria = models.CharField(
        max_length=20,
        choices=CATEGORIA_CHOICES,
        default="diferido",
        verbose_name="Categoría",
    )
    numero = models.CharField(max_length=50, verbose_name="Número de Cheque")
    banco = models.CharField(max_length=100, verbose_name="Banco Emisor")
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Monto")
    fecha_emision = models.DateField(
        default=timezone.now, verbose_name="Fecha de Emisión"
    )
    fecha_pago = models.DateField(verbose_name="Fecha de Pago (Vencimiento)")

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default="en_cartera",
        verbose_name="Estado",
    )

    cuit_emisor = models.CharField(
        max_length=20, blank=True, verbose_name="CUIT Emisor"
    )
    nombre_emisor = models.CharField(
        max_length=100, blank=True, verbose_name="Nombre Emisor"
    )

    contacto_origen = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cheques_entregados",
        verbose_name="Recibido de (Cliente)",
    )
    contacto_destino = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cheques_recibidos",
        verbose_name="Entregado a (Proveedor)",
    )

    class Meta:
        verbose_name = "Cheque"
        verbose_name_plural = "Cheques"
        ordering = ["fecha_pago"]

    def __str__(self):
        return (
            f"{self.get_tipo_display()} - {self.banco} #{self.numero} (${self.monto})"
        )


class TituloCreditoFCE(TimeStampedModel):
    """
    Título Ejecutivo y Activo Financiero derivado de una Factura de Crédito Electrónica MiPyME (Ley 27.440).
    Administra los 21 días de plazo para aceptación/rechazo en AFIP y su posterior negociación,
    cesión al FDI o descuento bancario/bursátil.
    """

    ESTADO_FCE_CHOICES = [
        ("emitida_pendiente", "Emitida (Pendiente en AFIP - 21 días)"),
        ("aceptada_expresa", "Aceptada Expresa (Título Ejecutivo Firme)"),
        ("aceptada_tacita", "Aceptada Tácita (Silencio Positivo AFIP)"),
        ("rechazada", "Rechazada por el Comprador"),
        ("cancelada_cliente", "Cancelada / Pagada Directamente por Cliente"),
        ("cedida_fdi", "Cedida al FDI (Fideicomiso de Desarrollo Industrial)"),
        ("descontada_banco", "Descontada en Banco / Factoring Bursátil"),
        ("cobrada", "Cobrada Totalmente"),
    ]

    SISTEMA_CIRCULACION_CHOICES = [
        ("SCA", "Sistema de Circulación Abierta (BCRA)"),
        ("ADC", "Agente de Depósito Colectivo (Caja de Valores)"),
    ]

    documento_deuda = models.OneToOneField(
        "contabilidad.DocumentoDeuda",
        on_delete=models.CASCADE,
        related_name="titulo_fce",
        verbose_name="Factura de Crédito MiPyME Origen",
    )

    estado = models.CharField(
        max_length=30,
        choices=ESTADO_FCE_CHOICES,
        default="emitida_pendiente",
        verbose_name="Estado de la FCE en AFIP",
    )

    sistema_circulacion = models.CharField(
        max_length=10,
        choices=SISTEMA_CIRCULACION_CHOICES,
        default="SCA",
        verbose_name="Sistema de Circulación",
    )

    fecha_notificacion_dfe = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de Notificación DFE",
        help_text="Fecha en que la factura fue notificada en el Domicilio Fiscal Electrónico del comprador.",
    )

    fecha_limite_aceptacion = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha Límite para Aceptación Tácita",
        help_text="Fecha máxima (21 días corridos) antes de que opere la aceptación de oficio en AFIP.",
    )

    fecha_aceptacion = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha Efectiva de Aceptación",
    )

    causal_rechazo = models.TextField(
        blank=True,
        verbose_name="Motivo / Causal de Rechazo en AFIP",
        help_text="Causal taxativa de la Ley 27.440 informada por el comprador si fue rechazada.",
    )

    # Cesión y descuento financiero
    tenedor_actual = models.CharField(
        max_length=150,
        blank=True,
        default="Emisor Original",
        verbose_name="Tenedor del Título",
        help_text="Ej: 'FDI FIMCA', 'Banco Provincia', 'Caja de Valores'.",
    )

    monto_neto_negociable = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Monto Neto Negociable",
        help_text="Monto neto de la factura descontadas retenciones preliminares.",
    )

    class Meta:
        verbose_name = "Título de Crédito FCE (Factura MiPyME)"
        verbose_name_plural = "Títulos de Crédito FCE (Facturas MiPyME)"
        ordering = ["-fecha_limite_aceptacion", "-id"]

    def __str__(self):
        return f"FCE #{self.documento_deuda.numero} - {self.get_estado_display()} (${self.monto_neto_negociable})"

    @property
    def es_titulo_ejecutivo_firme(self) -> bool:
        """Indica si el título ya puede ser descontado, transferido o ejecutado judicialmente."""
        return self.estado in ["aceptada_expresa", "aceptada_tacita", "cedida_fdi", "descontada_banco"]

