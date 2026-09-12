import json
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.db.models import Sum
from apps.base.models import TimeStampedModel, DocumentoBase


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


from apps.base.models import TimeStampedModel, DocumentoBase, DocumentoFirmableMixin


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
    contacto = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        verbose_name="Cliente / Proveedor",
    )
    escrow_asociado = models.ForeignKey(
        "tesoreria.ContratoEscrow",
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
        help_text="Útil para auditoría y conciliación de pagos de impuestos o transferencias agrupadas."
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


class IndiceUCI(TimeStampedModel):
    """
    Índice de la Unidad de Cuenta Industrial (UCI) respecto al IPIM o inflación sectorial.
    Garantiza que los fondos bloqueados no se carbonicen por inflación.
    """

    fecha = models.DateField(unique=True, verbose_name="Fecha de Cotización")
    valor_ars = models.DecimalField(
        max_digits=12, decimal_places=4, verbose_name="Valor en ARS"
    )

    class Meta:
        verbose_name = "Cotización UCI"
        verbose_name_plural = "Cotizaciones UCI"
        ordering = ["-fecha"]

    def __str__(self):
        return f"UCI {self.fecha}: $ {self.valor_ars}"


class ContratoEscrow(TimeStampedModel):
    """
    Contrato de bloqueo de fondos (Escrow) vinculado a una e-OP.
    Garantiza el repago al FDI o el desembolso seguro al tallerista por tramos.
    """

    ESTADO_CHOICES = [
        ("borrador", "Borrador / Pendiente de Fondeo"),
        ("fondeado", "Fondeado Activo (Capital bloqueado)"),
        ("ejecutando", "Ejecución por Hitos"),
        ("liquidado", "Liquidado (Tallerista Pagado)"),
        ("repago_completado", "Repago Completado (Cerrado)"),
        ("disputa", "En Disputa / Congelado"),
    ]

    # ForeignKey indirecto a la OrdenProduccion (se usa el UUID para el puente lógico si fuera necesario desacoplar)
    eop_uuid = models.UUIDField(unique=True, verbose_name="UUID e-OP vinculada")

    # Total comprometido
    monto_total_uci = models.DecimalField(
        max_digits=15, decimal_places=2, verbose_name="Monto Total a Custodiar (UCI)"
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="borrador")

    # Comprobante original con el que el comitente inyectó la plata al sistema
    comprobante_fondeo = models.ForeignKey(
        ComprobanteTesoreria, on_delete=models.RESTRICT, null=True, blank=True
    )

    class Meta:
        verbose_name = "Contrato Escrow"
        verbose_name_plural = "Contratos Escrow"

    def __str__(self):
        return f"Escrow e-OP {self.eop_uuid} [{self.get_estado_display()}]"


class HitoEscrow(DocumentoFirmableMixin, TimeStampedModel):
    """
    Tramos de liberación de fondos (Ej: Hito 0 (Anticipo 35%), Hito 1 (Avance), Hito Final).
    Hereda de DocumentoFirmableMixin para requerir firma criptográfica del PTF/Auditor.
    """

    contrato = models.ForeignKey(
        ContratoEscrow, on_delete=models.CASCADE, related_name="hitos"
    )
    nombre = models.CharField(
        max_length=100, help_text="Ej: Hito 0 - Anticipo de Arranque"
    )
    porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="Porcentaje del total del contrato"
    )

    requiere_auditoria_ptf = models.BooleanField(
        default=True,
        verbose_name="Requiere Firma PTF",
        help_text="Si está activo, el hito no se libera sin la firma criptográfica del Promotor Territorial.",
    )

    estado = models.CharField(
        max_length=20,
        choices=[
            ("bloqueado", "Bloqueado"),
            ("liberado", "Liberado al Taller"),
            ("reintegrado", "Reintegrado al FDI"),
        ],
        default="bloqueado",
    )

    # Comprobante de pago que se genera automáticamente al liberar el hito
    comprobante_pago = models.ForeignKey(
        ComprobanteTesoreria, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "Hito de Escrow"
        verbose_name_plural = "Hitos de Escrow"
        ordering = ["id"]

    def __str__(self):
        return f"{self.nombre} ({self.porcentaje}%) - {self.get_estado_display()}"

    def generar_payload_canonico(self):
        payload = {
            "uuid": str(self.uuid_identificador),
            "contrato_uuid": str(self.contrato.eop_uuid),
            "nombre": self.nombre,
            "porcentaje": str(self.porcentaje),
            "estado": self.estado,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
