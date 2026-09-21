import json
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.base.models import DocumentoBase, DocumentoFirmableMixin, TimeStampedModel

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


class ContratoEOP(DocumentoFirmableMixin, DocumentoBase):
    """
    Título de Crédito Ejecutivo y Contrato Fiduciario de la Red Federada FIMCA.
    Opera como activo negociable colateralizable ante el FDI y la MES.
    """
    SECUENCIA_CODIGO = "eop.contrato"

    # Enlace débil/opcional a la manufactura local (NULL si la marca opera vía SAP/Tango)
    orden_produccion_local = models.OneToOneField(
        "produccion.OrdenProduccion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contrato_eop",
        verbose_name=_("Orden de Producción Física Local"),
        help_text=_("Asociación a la orden de planta en Indinopy. Si es NULL, la orden proviene de un ERP externo (Headless)."),
    )

    # Identidad y Ruteo en la Red Federada
    nodo_mes = models.CharField(
        max_length=100,
        verbose_name=_("Nodo MES de Destino"),
        help_text=_("Snapshot inmutable capturado automáticamente de ConfiguracionEmpresa al emitir"),
    )
    ptf_asignado = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="eops_fiscalizadas",
        verbose_name=_("PTF Asignado"),
    )
    
    ESTADO_ESCROW_CHOICES = [
        ("solicitado", _("Solicitud de Fondeo Enviada")),
        ("financiado_fdi", _("Financiado por FDI (Comitente en Deuda)")),
        ("aprobado_silencio", _("Aprobado por Silencio Positivo (48h)")),
        ("vetado_mes", _("Vetado por la MES")),
        ("hito_cero_liberado", _("Hito Cero Acreditado en Cuenta Taller")),
        ("en_disputa", _("En Disputa Arbitral (72h)")),
        ("liquidado_total", _("Liquidación Final Completada")),
    ]
    
    estado_escrow = models.CharField(
        max_length=30,
        choices=ESTADO_ESCROW_CHOICES,
        default="solicitado",
        verbose_name=_("Estado de Escrow / Custodia"),
    )
    fecha_fondeo_escrow = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Fecha de Fondeo / Inicio Timelock")
    )
    
    # Comprobante original con el que el comitente inyectó la plata al sistema (para repagos)
    # Vector C: Costos Homologados (en UCI o indexado)
    costo_mod = models.DecimalField(max_digits=15, decimal_places=2, default=0.0, verbose_name=_("MOD"))
    costo_cs = models.DecimalField(max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Cargas Sociales"))
    costo_bom = models.DecimalField(max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Insumos"))
    costo_fdi = models.DecimalField(max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Reserva FDI (2%)"))
    costo_tax = models.DecimalField(max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Monotributo / Tax"))
    costo_mg = models.DecimalField(max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Margen"))

    # Sello de Calidad
    es_sello_buen_diseno = models.BooleanField(default=False)

    # Árbol de Merkle del BOM inmutable (Snapshot estático)
    merkle_root_bom = models.CharField(max_length=64, blank=True, null=True)

    class Meta(DocumentoBase.Meta):
        verbose_name = _("Contrato e-OP Federado")
        verbose_name_plural = _("Contratos e-OP Federados")

    @property
    def monto_total_uci(self):
        """El monto total colateralizado es la suma del vector."""
        return sum([self.costo_mod, self.costo_cs, self.costo_bom, self.costo_fdi, self.costo_tax, self.costo_mg])

    def __str__(self):
        return f"e-OP {self.numero} [{self.get_estado_escrow_display()}]"


class EOPHitoEscrow(DocumentoFirmableMixin, TimeStampedModel):
    """
    Tramos de liberación de fondos de la e-OP.
    Hereda de DocumentoFirmableMixin para requerir firma criptográfica del PTF/Auditor.
    """

    contrato = models.ForeignKey(
        ContratoEOP, on_delete=models.CASCADE, related_name="hitos"
    )
    nombre = models.CharField(
        max_length=100, help_text="Ej: Hito Cero - Anticipo de Arranque, Corte Completo..."
    )
    porcentaje_tramo = models.DecimalField(
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
            ("fiscal_pending", "Retención de Cierre Fiscal (Esperando Factura)"),
            ("liberado", "Liberado al Taller"),
            ("reintegrado", "Reintegrado al FDI"),
        ],
        default="bloqueado",
    )

    requiere_verificacion_arca = models.BooleanField(
        default=False, 
        verbose_name=_("Requiere Factura Electrónica (ARCA)"),
        help_text=_("Si es True, el hito cae en FISCAL_PENDING hasta constatar factura.")
    )
    factura_asociada_arca = models.CharField(
        max_length=50, blank=True, null=True, 
        verbose_name=_("CAE / Nro Factura (ARCA)"),
        help_text=_("CAE o Número de comprobante validado o cargado por el tallerista.")
    )

    # Comprobante de pago que se genera automáticamente al liberar el hito
    comprobante_pago = models.ForeignKey(
        "tesoreria.ComprobanteTesoreria", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "Hito de Escrow e-OP"
        verbose_name_plural = "Hitos de Escrow e-OP"
        ordering = ["id"]

    def __str__(self):
        return f"{self.nombre} ({self.porcentaje_tramo}%) - {self.get_estado_display()}"

    def generar_payload_canonico(self):
        payload = {
            "uuid": str(self.uuid_identificador),
            "contrato_uuid": str(self.contrato.uuid_identificador),
            "nombre": self.nombre,
            "porcentaje_tramo": str(self.porcentaje_tramo),
            "estado": self.estado,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
