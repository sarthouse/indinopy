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
    # Vector C: 3 Vectores de Costos Homologados Oficiales (en UCI o indexado) - Art. 4° inc. 4
    costo_mod = models.DecimalField(
        max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Mano de Obra Directa (MOD)")
    )
    costo_bom = models.DecimalField(
        max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Insumos y Materias Primas en Custodia (BOM)"),
        help_text=_("Refleja los bienes en custodia de transformación (Art. 4 inc 4.b). No integra la deuda exigible.")
    )
    costo_fdi_operativo = models.DecimalField(
        max_digits=15, decimal_places=2, default=0.0, verbose_name=_("Canon FDI Operativo (1.5% max sobre MOD)")
    )
    costo_fdi_stock = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("0.00"),
        verbose_name=_("Alícuota Cobertura de Stock (0.5% max sobre BOM)")
    )

    MONEDA_CHOICES = [
        ("uci", _("Unidad de Cuenta Industrial (UCI - IPIM/Paritaria)")),
        ("uva", _("Unidad de Valor Adquisitivo (UVA)")),
        ("ars", _("Pesos Argentinos (ARS)")),
        ("usd", _("Dólares Estadounidenses (USD - Art. 765 CCyC)")),
    ]
    moneda_denominacion = models.CharField(
        max_length=10, choices=MONEDA_CHOICES, default="uci",
        verbose_name=_("Moneda / Unidad de Cuenta")
    )

    plazo_comercial_dias = models.PositiveIntegerField(
        default=60, choices=[(60, "60 días"), (90, "90 días"), (120, "120 días")],
        verbose_name=_("Plazo Comercial de Repago")
    )
    fecha_vencimiento_comercial = models.DateField(
        null=True, blank=True, verbose_name=_("Vencimiento Comercial Original")
    )
    fecha_vencimiento_recalculada = models.DateField(
        null=True, blank=True, verbose_name=_("Vencimiento Comercial Recalculado (JIT/Prórrogas)")
    )

    # Logística Justo a Tiempo (Art. 5° bis)
    es_justo_a_tiempo = models.BooleanField(
        default=False, verbose_name=_("Logística Justo a Tiempo (JIT)")
    )
    dias_mora_comitente_jit = models.PositiveIntegerField(
        default=0, verbose_name=_("Días de Mora Comitente JIT")
    )
    compensacion_standby_acumulada_ars = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        verbose_name=_("Compensación Standby Acumulada (ARS)")
    )

    # Confesión de Deuda Hito Cero (Art. 6°)
    declaracion_confesion_deuda_hito_cero = models.BooleanField(
        default=False, verbose_name=_("Confesión de Deuda Hito Cero Aceptada")
    )

    # Sello de Calidad
    es_sello_buen_diseno = models.BooleanField(default=False)

    # Árbol de Merkle del BOM inmutable (Snapshot estático)
    merkle_root_bom = models.CharField(max_length=64, blank=True, null=True)

    class Meta(DocumentoBase.Meta):
        verbose_name = _("Contrato e-OP Federado")
        verbose_name_plural = _("Contratos e-OP Federados")

    def __init__(self, *args, **kwargs):
        # Retrocompatibilidad con instancias o pruebas que asignan costo_fdi
        if "costo_fdi" in kwargs and "costo_fdi_operativo" not in kwargs:
            kwargs["costo_fdi_operativo"] = kwargs.pop("costo_fdi")
        elif "costo_fdi" in kwargs:
            kwargs.pop("costo_fdi")
        super().__init__(*args, **kwargs)

    @property
    def costo_fdi(self):
        """Canon total fiduciario estructurado a cargo de la comitente."""
        return (self.costo_fdi_operativo or Decimal("0.00")) + (self.costo_fdi_stock or Decimal("0.00"))

    @costo_fdi.setter
    def costo_fdi(self, value):
        self.costo_fdi_operativo = Decimal(str(value or 0))

    @property
    def monto_total_uci(self):
        """
        Monto exigible del título valor causal:
        Mano de Obra Directa (MOD) + Canon fiduciario estructurado.
        Excluye expresamente el valor de los insumos provistos (BOM) s/Art. 4° inc. 4.b.
        """
        return self.costo_mod + self.costo_fdi

    @property
    def valor_declarado_custodia_bom(self):
        """Refleja el valor de los insumos provistos en custodia de transformación."""
        return self.costo_bom

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
                "remito_oficial_uuid": hito.remito_oficial_uuid or "",
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
            "moneda_denominacion": self.moneda_denominacion,
            "plazo_comercial_dias": self.plazo_comercial_dias,
            "fecha_vencimiento_comercial": str(self.fecha_vencimiento_comercial or ""),
            "cotizacion_uci_ars": str(cotizacion_uci),
            "monto_total_uci": str(self.monto_total_uci),
            "monto_financiado_fdi_uci": str(self.monto_total_uci),
            "vector_costos": {
                "mod_servicios": str(self.costo_mod),
                "canon_fdi_operativo": str(self.costo_fdi_operativo),
                "canon_fdi_stock": str(self.costo_fdi_stock),
                "canon_fdi_mes": str(self.costo_fdi),
                "insumos_bom": str(self.costo_bom),
            },
            "es_sello_buen_diseno": bool(self.es_sello_buen_diseno),
            "es_justo_a_tiempo": bool(self.es_justo_a_tiempo),
            "clausula_confesion_deuda_h0": bool(self.declaracion_confesion_deuda_hito_cero),
            "merkle_root_bom": merkle_root,
            "cronograma_escrow_hitos": hitos_data,
            "etapas_productivas": etapas_data,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def __str__(self):
        return f"e-OP {self.numero} [{self.get_estado_escrow_display()}]"


class IncidenciaLogisticaJIT(TimeStampedModel):
    """
    Registro de contingencias y demoras en provisión de insumos Justo a Tiempo (Art. 5° bis).
    """
    contrato = models.ForeignKey(
        ContratoEOP, on_delete=models.CASCADE, related_name="incidencias_jit"
    )
    etapa_afectada = models.CharField(max_length=100, verbose_name=_("Etapa Afectada"))
    fecha_entrega_esperada = models.DateField(verbose_name=_("Fecha de Entrega Esperada"))
    fecha_entrega_real = models.DateField(null=True, blank=True, verbose_name=_("Fecha de Entrega Real"))
    dias_demora = models.PositiveIntegerField(default=0, verbose_name=_("Días de Demora"))
    compensacion_standby_devengada = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        verbose_name=_("Compensación Standby (ARS)"),
        help_text=_("0.5 SMVM por día hábil a partir del 6° día de mora.")
    )
    resolucion_ejercida_por_taller = models.BooleanField(
        default=False, verbose_name=_("Resolución Contractual Ejercida por Taller")
    )

    class Meta:
        verbose_name = _("Incidencia Logística JIT")
        verbose_name_plural = _("Incidencias Logística JIT")
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Incidencia JIT {self.contrato} - {self.dias_demora} días"


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
        max_length=30,
        choices=[
            ("bloqueado", "Bloqueado"),
            ("retencion_cierre_fiscal", "Retención de Cierre Fiscal (Esperando Factura)"),
            ("liberado", "Liberado al Taller"),
            ("reintegrado", "Reintegrado al FDI"),
        ],
        default="bloqueado",
    )

    # Acreditación PoPW (Hitos de Avance) y Hito Cero (Art. 12°)
    ddjj_avance_datos = models.JSONField(
        default=dict, blank=True, verbose_name=_("DDJJ Avance de Curva")
    )
    georreferenciacion_satelital = models.CharField(
        max_length=255, blank=True, null=True, verbose_name=_("Georreferenciación Satelital Cifrada")
    )
    remito_oficial_uuid = models.CharField(
        max_length=64, blank=True, null=True, verbose_name=_("UUID / Nro Remito Oficial de Insumos")
    )
    seguro_stock_verificado = models.BooleanField(
        default=False, verbose_name=_("Seguro de Stock Verificado (Art. 20 bis)")
    )

    # Retención de Cierre Fiscal (RCF - Hito Final)
    requiere_verificacion_arca = models.BooleanField(
        default=False, 
        verbose_name=_("Requiere Factura Electrónica (ARCA)"),
        help_text=_("Si es True, el hito cae en retención de cierre fiscal hasta constatar factura.")
    )
    factura_asociada_arca = models.CharField(
        max_length=50, blank=True, null=True, 
        verbose_name=_("CAE / Nro Factura (ARCA)"),
        help_text=_("CAE o Número de comprobante validado o cargado por el tallerista.")
    )
    fecha_entrega_lote_conforme = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Fecha de Entrega Conforme de Lote")
    )
    fecha_limite_facturacion = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Fecha Límite Facturación (10 días hábiles)")
    )
    cargo_mora_badlar_devengado = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        verbose_name=_("Cargo Mora BADLAR Devengado")
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
