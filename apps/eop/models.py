import json
from decimal import Decimal
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
    # Vector C: 3 Vectores de Costos Homologados Oficiales (en UCI o indexado)
    costo_mod = models.DecimalField(
        max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Mano de Obra Directa (MOD)")
    )
    costo_bom = models.DecimalField(
        max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Insumos y Materias Primas (BOM)")
    )
    costo_fdi = models.DecimalField(
        max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Canon de Red MES / Reserva FDI (1.5%)")
    )

    # Sello de Calidad
    es_sello_buen_diseno = models.BooleanField(default=False)

    # Árbol de Merkle del BOM inmutable (Snapshot estático)
    merkle_root_bom = models.CharField(max_length=64, blank=True, null=True)

    class Meta(DocumentoBase.Meta):
        verbose_name = _("Contrato e-OP Federado")
        verbose_name_plural = _("Contratos e-OP Federados")

    @property
    def monto_total_uci(self):
        """El monto total colateralizado es la suma de los 3 vectores válidos (MOD + BOM + FDI)."""
        return sum([self.costo_mod, self.costo_bom, self.costo_fdi])

    def calcular_merkle_root_bom(self):
        """
        Calcula el árbol de Merkle inmutable del BOM / insumos de la orden asociada.
        Si la OP es headless, utiliza bom_headless. Si tiene receta o insumos requeridos,
        hashea cada ítem individualmente y los combina en pares.
        """
        import hashlib
        leaves = []
        if self.orden_produccion_local:
            op = self.orden_produccion_local
            if op.bom_headless and isinstance(op.bom_headless, list):
                for item in op.bom_headless:
                    item_str = json.dumps(item, sort_keys=True, separators=(",", ":"))
                    leaves.append(hashlib.sha256(item_str.encode("utf-8")).hexdigest())
            else:
                insumos = op.insumos_requeridos.all().order_by("id")
                for req in insumos:
                    leaf_str = f"{req.insumo_id}:{str(req.cantidad_teorica)}:{req.origen}"
                    leaves.append(hashlib.sha256(leaf_str.encode("utf-8")).hexdigest())

        if not leaves:
            return hashlib.sha256(b"empty_bom").hexdigest()

        # Armado binario del árbol de Merkle
        current_layer = sorted(leaves)
        while len(current_layer) > 1:
            next_layer = []
            for i in range(0, len(current_layer), 2):
                if i + 1 < len(current_layer):
                    combined = current_layer[i] + current_layer[i + 1]
                else:
                    combined = current_layer[i] + current_layer[i]
                next_layer.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
            current_layer = next_layer
        return current_layer[0]

    def generar_payload_canonico(self):
        """
        Genera el string JSON determinista de la e-OP para firma Ed25519 y validación MES.
        Incluye CUITs, Vector C, total UCI, Merkle Root del BOM y cronograma dinámico de hitos.
        """
        from apps.base.models import ConfiguracionEmpresa

        empresa = ConfiguracionEmpresa.objects.first()
        comitente_cuit = empresa.cuit if empresa else ""

        taller_cuit = ""
        if self.ptf_asignado and self.ptf_asignado.cuil:
            taller_cuit = self.ptf_asignado.cuil
        elif self.orden_produccion_local:
            primer_etapa = self.orden_produccion_local.tracking_etapas.filter(
                tallerista_asignado__isnull=False
            ).first()
            if primer_etapa and primer_etapa.tallerista_asignado.cuil:
                taller_cuit = primer_etapa.tallerista_asignado.cuil

        hitos_data = []
        for hito in self.hitos.all().order_by("id"):
            hitos_data.append({
                "uuid": str(hito.uuid_identificador),
                "nombre": hito.nombre,
                "porcentaje_tramo": str(hito.porcentaje_tramo),
                "requiere_auditoria_ptf": bool(hito.requiere_auditoria_ptf),
                "requiere_verificacion_arca": bool(hito.requiere_verificacion_arca),
            })

        etapas_data = []
        if self.orden_produccion_local:
            for etapa in self.orden_produccion_local.tracking_etapas.all().order_by("etapa_origen__orden_ejecucion", "id"):
                taller = etapa.tallerista_asignado
                etapas_data.append({
                    "orden": etapa.etapa_origen.orden_ejecucion if etapa.etapa_origen else 0,
                    "servicio": etapa.etapa_origen.servicio.nombre if (etapa.etapa_origen and etapa.etapa_origen.servicio) else "S/D",
                    "tallerista": {
                        "cuit": taller.cuil if (taller and taller.cuil) else "",
                        "razon_social": taller.nombre if taller else "",
                        "cuenta_clearing_cbu": taller.cbu_alias if (taller and taller.cbu_alias) else "",
                    },
                    "costo_servicio": str(etapa.costo_servicio_total or Decimal("0.00")),
                })

        merkle_root = self.merkle_root_bom or self.calcular_merkle_root_bom()

        from apps.eop.services import UCIService
        cotizacion_uci = UCIService.obtener_cotizacion_actual()

        payload = {
            "protocolo_version": "2.0",
            "uuid_identificador": str(self.uuid_identificador),
            "numero_contrato": self.numero or "",
            "nodo_mes": self.nodo_mes or "",
            "comitente_cuit": comitente_cuit,
            "tallerista_cuit": taller_cuit,
            "cotizacion_uci_ars": str(cotizacion_uci),
            "monto_total_uci": str(self.monto_total_uci),
            "monto_financiado_fdi_uci": str(self.costo_mod + self.costo_fdi),
            "vector_costos": {
                "mod_servicios": str(self.costo_mod),
                "canon_fdi_mes": str(self.costo_fdi),
                "insumos_bom": str(self.costo_bom),
            },
            "es_sello_buen_diseno": bool(self.es_sello_buen_diseno),
            "merkle_root_bom": merkle_root,
            "cronograma_escrow_hitos": hitos_data,
            "etapas_productivas": etapas_data,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

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

    def clean(self):
        super().clean()
        if self.porcentaje_tramo is not None:
            if self.porcentaje_tramo <= Decimal("0.00") or self.porcentaje_tramo > Decimal("100.00"):
                from django.core.exceptions import ValidationError
                raise ValidationError({
                    "porcentaje_tramo": _("El porcentaje del tramo debe ser un valor positivo mayor a 0 y menor o igual a 100.")
                })

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
