import hashlib
import json
import uuid
import uuid6
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from apps.base.models import TimeStampedModel, DocumentoBase, DocumentoFirmableMixin
from apps.base.services import SecuenciaService
from apps.inventario.models import (
    ProductoTemplate,
    Producto,
    AtributoValor,
    Ubicacion,
    MovimientoStock,
    LineaMovimientoStock,
    StockQuant,
)


class Receta(TimeStampedModel):
    """
    Ficha Técnica (BOM - Bill of Materials).
    Define la plantilla maestra de cómo se fabrica un modelo.
    """

    producto_template = models.ForeignKey(
        ProductoTemplate,
        on_delete=models.CASCADE,
        related_name="recetas",
        verbose_name=_("Producto base"),
    )
    nombre_version = models.CharField(
        max_length=100,
        verbose_name=_("Versión / Colección"),
        help_text=_("Ej: Invierno 2024, Reforzado, Base Exportación"),
    )
    observaciones_generales = models.TextField(
        blank=True, null=True, verbose_name=_("Observaciones generales")
    )
    activa = models.BooleanField(default=True, verbose_name=_("Activa"))

    class Meta:
        verbose_name = _("Ficha Técnica (Receta)")
        verbose_name_plural = _("Fichas Técnicas (Recetas)")
        ordering = ["producto_template__nombre", "-creado_en"]

    def __str__(self):
        return f"Receta: {self.producto_template.nombre} ({self.nombre_version})"


class RecetaInsumo(TimeStampedModel):
    """Lista de insumos requeridos teóricamente por cada 1 unidad/par a fabricar."""

    receta = models.ForeignKey(
        Receta,
        on_delete=models.CASCADE,
        related_name="insumos",
        verbose_name=_("Receta"),
    )
    insumo = models.ForeignKey(
        Producto,
        on_delete=models.RESTRICT,
        verbose_name=_("Insumo (Materia prima / Consumible)"),
    )
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name=_("Cantidad base requerida"),
        help_text=_(
            "Consumo unitario por par/pieza (ej: 0.25 m2 de cuero, 0.05 l de pegamento)"
        ),
    )
    porcentaje_merma_tolerada = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        verbose_name=_("Merma técnica tolerable (%)"),
        help_text=_(
            "Estándar INTI de descarte admisible en corte y aparado (hasta 10%)"
        ),
    )
    variantes_destino = models.ManyToManyField(AtributoValor, blank=True)

    class Meta:
        verbose_name = _("Insumo de receta")
        verbose_name_plural = _("Insumos de receta")

    def __str__(self):
        return f"{self.insumo} - {self.cantidad} {self.insumo.template.unidad_medida}"


class RecetaEtapa(TimeStampedModel):
    """Hoja de ruta teórica de etapas de fabricación."""

    receta = models.ForeignKey(
        Receta,
        on_delete=models.CASCADE,
        related_name="etapas",
        verbose_name=_("Receta"),
    )
    orden_ejecucion = models.PositiveIntegerField(verbose_name=_("Orden de ejecución"))
    servicio = models.ForeignKey(
        ProductoTemplate,
        on_delete=models.RESTRICT,
        verbose_name=_("Servicio / Proceso"),
        help_text=_(
            "ProductoTemplate de tipo 'Servicio' (ej: Corte, Rebajado, Aparado)"
        ),
    )
    observaciones_proceso = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Instrucciones técnicas"),
        help_text=_(
            "Observaciones que viajarán al tallerista en el duplicado de la OP"
        ),
    )
    porcentaje_hito_pago = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        verbose_name=_("% de Pago al finalizar etapa"),
        help_text=_(
            "Define el cronograma de liberación de fondos (Ej: 20% al terminar Corte)"
        ),
    )

    class Meta:
        verbose_name = _("Etapa de receta")
        verbose_name_plural = _("Etapas de receta")
        ordering = ["orden_ejecucion"]

    def __str__(self):
        return f"{self.orden_ejecucion}. {self.servicio.nombre}"


# ==========================================
# MODELOS DE EJECUCIÓN (PRODUCCIÓN REAL)
# ==========================================


class OrdenProduccion(DocumentoBase):
    """
    Documento rector de la fabricación del Lote.
    Hereda de DocumentoBase y DocumentoFirmableMixin.
    """

    SECUENCIA_CODIGO = "produccion.op"

    SUBESTADO_CHOICES = [
        ("espera", _("En Espera")),
        ("cortado", _("En Cortado")),
        ("rebajado", _("En Rebajado")),
        ("aparado", _("En Aparado")),
        ("armado", _("En Armado")),
    ]

    TIPO_PRODUCCION = [
        ("interna", _("Producción Interna / Talleres controlados")),
        ("fason", _("A Fasón (Tercerización externa)")),
    ]

    @property
    def es_eop_federada(self):
        """Devuelve True si esta OP está vinculada a un Smart Contract FIMCA."""
        return hasattr(self, "contrato_eop")

    fecha_entrega = models.DateField(
        blank=True, null=True, verbose_name=_("Fecha est. entrega")
    )
    receta = models.ForeignKey(
        Receta,
        on_delete=models.RESTRICT,
        related_name="ordenes_produccion",
        verbose_name=_("Receta base"),
        null=True,
        blank=True,
        help_text=_("Opcional en Modo Headless (cuando el BOM viene del ERP legacy)"),
    )
    bom_headless = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("BOM Externo (Headless)"),
        help_text=_("Guarda la lista de materiales teórica inyectada por API externa"),
    )
    cliente = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_produccion",
        verbose_name=_("Cliente / Distribuidor"),
        help_text=_(
            "Opcional: Si se deja en blanco, la producción es para Stock Propio"
        ),
    )
    cantidad_total = models.PositiveIntegerField(
        verbose_name=_("Cantidad total a fabricar")
    )
    cantidad_producida = models.PositiveIntegerField(
        default=0, verbose_name=_("Cantidad total producida hasta la fecha")
    )

    tipo = models.CharField(
        max_length=20,
        choices=TIPO_PRODUCCION,
        default="interna",
        verbose_name=_("Tipo de producción"),
        help_text=_(
            "Define si controlamos el stock o si el fasón gestiona sus compras"
        ),
    )
    subestado = models.CharField(
        max_length=20,
        choices=SUBESTADO_CHOICES,
        default="espera",
        verbose_name=_("Subestado operativo"),
    )
    # El estado fiduciario ahora vive en ContratoEOP

    # === Protocolo e-OP ===
    # El ptf_asignado ahora se define en el ContratoEOP

    # Los costos inmutables del Vector C (mod, cs, bom, etc) se movieron a ContratoEOP

    # Sello Buen Diseño y Firmas criptográficas pasaron a ContratoEOP

    class Meta(DocumentoBase.Meta):
        verbose_name = _("Orden de Producción (OP)")
        verbose_name_plural = _("Órdenes de Producción (OPs)")
        permissions = [
            (
                "view_costos_op",
                "Puede ver los costos e insumos valorizados de la OP (Original)",
            ),
            ("aprobar_op", "Puede aprobar la OP para inicio de fabricación"),
        ]

    def __str__(self):
        cliente_nombre = ""
        if self.cliente:
            cliente_nombre = (
                f" - {self.cliente.razon_social or self.cliente.nombre_fantasia}"
            )
        template_nombre = (
            self.receta.producto_template.nombre
            if self.receta and self.receta.producto_template
            else "S/D"
        )
        return f"OP {self.numero} - {template_nombre}{cliente_nombre} ({self.cantidad_producida}/{self.cantidad_total})"

    def clean(self):
        super().clean()

    @property
    def porcentaje_avance(self):
        if self.cantidad_total > 0:
            return round(
                (Decimal(self.cantidad_producida) / Decimal(self.cantidad_total))
                * Decimal("100.0"),
                1,
            )
        return Decimal("0.0")

    def registrar_produccion_parcial(
        self, variaciones_cantidades, observaciones="", usuario=None
    ):
        """
        Registra la finalización parcial de una tanda de la OP.
        - variaciones_cantidades: dict con {op_variacion_id: cantidad_producida}
        """
        with transaction.atomic():
            almacen, _ = Ubicacion.objects.get_or_create(
                tipo="interna", defaults={"nombre": "Almacén Principal", "activa": True}
            )
            ubicacion_produccion, _ = Ubicacion.objects.get_or_create(
                tipo="produccion",
                defaults={"nombre": "Fábrica (Virtual)", "activa": True},
            )

            num_parte = self.partes_produccion.count() + 1
            ct = ContentType.objects.get_for_model(self)

            remito_terminados = MovimientoStock.objects.create(
                numero=f"ING-{self.numero}-P{num_parte}",
                tipo="recepcion",
                estado="finalizado",
                ubicacion_origen=ubicacion_produccion,
                ubicacion_destino=almacen,
                contacto=self.cliente,
                responsable=usuario,
                content_type_origen=ct,
                object_id_origen=self.id,
                documento_origen=self.numero,
                observaciones=f"Entrega parcial {num_parte} de OP {self.numero}. {observaciones}",
            )

            parte = OPParteProduccion.objects.create(
                op=self,
                numero_parte=f"PARTE-{self.numero}-{num_parte:02d}",
                responsable=usuario,
                movimiento_terminados=remito_terminados,
                observaciones=observaciones,
            )

            total_tanda = 0
            for var_id, data in variaciones_cantidades.items():
                if isinstance(data, dict):
                    qty_primera = int(data.get("primera", 0))
                    qty_segunda = int(data.get("segunda", 0))
                    qty_descarte = int(data.get("descarte", 0))
                else:
                    qty_primera = int(data)
                    qty_segunda = 0
                    qty_descarte = 0

                qty_efectiva = qty_primera + qty_segunda
                if qty_efectiva <= 0 and qty_descarte <= 0:
                    continue

                var = self.variaciones.select_for_update().get(id=var_id)
                var.cantidad_producida += qty_efectiva
                var.save()
                total_tanda += qty_efectiva

                OPParteProduccionLinea.objects.create(
                    parte=parte,
                    variacion=var,
                    cantidad=qty_primera,
                    cantidad_segunda=qty_segunda,
                    cantidad_descarte=qty_descarte,
                )

                if qty_efectiva > 0:
                    ref_str = f"Tanda {num_parte} OP {self.numero}"
                    if qty_segunda > 0:
                        ref_str += f" ({qty_primera} 1ra / {qty_segunda} 2da)"
                    LineaMovimientoStock.objects.create(
                        movimiento=remito_terminados,
                        producto=var.producto,
                        cantidad=Decimal(qty_efectiva),
                        cantidad_hecha=Decimal(qty_efectiva),
                        ubicacion_origen=ubicacion_produccion,
                        ubicacion_destino=almacen,
                        estado="realizado",
                        referencia=ref_str,
                    )

            # Consumir insumos proporcionales de la reserva
            remito_reserva = MovimientoStock.objects.filter(
                numero=f"RES-{self.numero}"
            ).first()
            if remito_reserva and self.cantidad_total > self.cantidad_producida:
                factor = Decimal(total_tanda) / Decimal(
                    self.cantidad_total - self.cantidad_producida
                )
                for linea_res in list(remito_reserva.lineas.filter(estado="reservado")):
                    qty_a_consumir = linea_res.cantidad * factor
                    if qty_a_consumir > 0:
                        LineaMovimientoStock.objects.create(
                            movimiento=remito_reserva,
                            producto=linea_res.producto,
                            cantidad=qty_a_consumir,
                            cantidad_hecha=qty_a_consumir,
                            ubicacion_origen=linea_res.ubicacion_origen,
                            ubicacion_destino=linea_res.ubicacion_destino,
                            estado="realizado",
                            referencia=f"Consumo tanda {num_parte} OP {self.numero}",
                        )
                        linea_res.cantidad = max(
                            Decimal("0.0"), linea_res.cantidad - qty_a_consumir
                        )
                        if linea_res.cantidad == 0:
                            linea_res.delete()
                        else:
                            linea_res.save()

            self.cantidad_producida += total_tanda
            if self.cantidad_producida >= self.cantidad_total:
                self.estado = "finalizado"
            elif self.estado == "borrador":
                self.estado = "confirmado"
            self.save()

            return parte

    def cerrar_con_faltantes(self, motivo="", usuario=None):
        """
        Cierra la OP reconociendo mermas o scrap si no se alcanza la cantidad_total.
        Libera cualquier insumo reservado remanente en inventario.
        """
        with transaction.atomic():
            remito_reserva = MovimientoStock.objects.filter(
                numero=f"RES-{self.numero}"
            ).first()
            if remito_reserva:
                for linea_res in remito_reserva.lineas.filter(estado="reservado"):
                    linea_res.estado = "cancelado"
                    linea_res.save()
                remito_reserva.estado = "finalizado"
                remito_reserva.save()

            self.estado = "finalizado"
            nota_cierre = f"\n[Cierre con faltantes]: Producidos {self.cantidad_producida}/{self.cantidad_total}. Motivo: {motivo}"
            self.observaciones = (self.observaciones or "") + nota_cierre
            self.save()

    @property
    def costo_total_insumos_teorico(self):
        """Calcula el costo teórico acumulado de los insumos requeridos."""
        total = Decimal("0.00")
        for req in self.insumos_requeridos.all():
            costo_unit = (
                req.insumo.template.costo
                if req.insumo and req.insumo.template
                else Decimal("0.00")
            )
            total += req.cantidad_teorica * costo_unit
        return round(total, 2)

    @property
    def costo_total_insumos_real(self):
        """Calcula el costo real de los insumos consumidos si fue asentada la merma real."""
        total = Decimal("0.00")
        for req in self.insumos_requeridos.all():
            cant = (
                req.cantidad_consumida_real
                if req.cantidad_consumida_real is not None
                else req.cantidad_teorica
            )
            costo_unit = (
                req.insumo.template.costo
                if req.insumo and req.insumo.template
                else Decimal("0.00")
            )
            total += cant * costo_unit
        return round(total, 2)

    @property
    def costo_total_fason(self):
        """Suma las liquidaciones y costos de servicios de talleristas registrados en tracking."""
        return sum(
            (
                etapa.costo_servicio_total or Decimal("0.00")
                for etapa in self.tracking_etapas.all()
            ),
            Decimal("0.00"),
        )

    @property
    def costo_total_estimado(self):
        """Costo total consolidado (Insumos consumidos + Servicios de Fasón / Mano de obra)."""
        return self.costo_total_insumos_real + self.costo_total_fason

    @property
    def costo_unitario_par(self):
        """Costo industrial real resultante por par terminado."""
        cant = self.cantidad_producida or self.cantidad_total
        if cant > 0:
            return round(self.costo_total_estimado / Decimal(cant), 2)
        return Decimal("0.00")

    def generar_devolucion_sobrantes(
        self, insumos_cantidades, usuario=None, observaciones=""
    ):
        """
        Genera un remito de retorno de insumos no consumidos desde la fábrica virtual
        hacia el Almacén Principal.
        - insumos_cantidades: dict {insumo_sku_id: cantidad_a_devolver}
        """
        with transaction.atomic():
            almacen, _ = Ubicacion.objects.get_or_create(
                tipo="interna", defaults={"nombre": "Almacén Principal", "activa": True}
            )
            ubicacion_produccion, _ = Ubicacion.objects.get_or_create(
                tipo="produccion",
                defaults={"nombre": "Fábrica (Virtual)", "activa": True},
            )

            num_dev = (
                MovimientoStock.objects.filter(
                    documento_origen=self.numero,
                    tipo="traslado",
                    numero__startswith=f"DEV-{self.numero}",
                ).count()
                + 1
            )
            ct = ContentType.objects.get_for_model(self)

            remito_dev = MovimientoStock.objects.create(
                numero=f"DEV-{self.numero}-{num_dev:02d}",
                tipo="traslado",
                estado="finalizado",
                ubicacion_origen=ubicacion_produccion,
                ubicacion_destino=almacen,
                responsable=usuario,
                content_type_origen=ct,
                object_id_origen=self.id,
                documento_origen=self.numero,
                observaciones=f"Devolución de sobrantes de insumos de OP {self.numero}. {observaciones}",
            )

            for insumo_id, qty in insumos_cantidades.items():
                qty = Decimal(str(qty))
                if qty <= Decimal("0.0"):
                    continue
                producto_insumo = Producto.objects.get(id=insumo_id)
                LineaMovimientoStock.objects.create(
                    movimiento=remito_dev,
                    producto=producto_insumo,
                    cantidad=qty,
                    cantidad_hecha=qty,
                    ubicacion_origen=ubicacion_produccion,
                    ubicacion_destino=almacen,
                    estado="realizado",
                    referencia=f"Sobrante devuelto OP {self.numero}",
                )

            return remito_dev

    # Los métodos calcular_merkle_root_bom y generar_payload_canonico
    # han sido movidos a ContratoEOP.


class OPVariacion(TimeStampedModel):
    """Curva de talles/colores específica asignada a este lote."""

    op = models.ForeignKey(
        OrdenProduccion,
        on_delete=models.CASCADE,
        related_name="variaciones",
        verbose_name=_("Orden de producción"),
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.RESTRICT,
        related_name="variaciones_op",
        verbose_name=_("Producto (SKU / Variante)"),
    )
    cantidad = models.PositiveIntegerField(verbose_name=_("Cantidad a fabricar"))
    cantidad_producida = models.PositiveIntegerField(
        default=0, verbose_name=_("Cantidad ya fabricada")
    )

    class Meta:
        verbose_name = _("Variación de OP (Curva)")
        verbose_name_plural = _("Variaciones de OP (Curva de talles)")

    @property
    def cantidad_pendiente(self):
        return max(0, self.cantidad - self.cantidad_producida)

    def __str__(self):
        return f"{self.producto} x {self.cantidad} (Hecho: {self.cantidad_producida})"


class OPInsumoRequerido(TimeStampedModel):
    """Insumos comprometidos o consumidos realmente por este lote."""

    ORIGEN_INSUMO_CHOICES = [
        ("empresa", _("Stock Propio (Descuenta Almacén)")),
        ("fabrica", _("Provisto por Taller/Fasón (Genera Deuda)")),
    ]

    op = models.ForeignKey(
        OrdenProduccion,
        on_delete=models.CASCADE,
        related_name="insumos_requeridos",
        verbose_name=_("Orden de producción"),
    )
    insumo = models.ForeignKey(
        Producto,
        on_delete=models.RESTRICT,
        related_name="requerimientos_op",
        verbose_name=_("Insumo (SKU)"),
    )
    origen = models.CharField(
        max_length=20,
        choices=ORIGEN_INSUMO_CHOICES,
        default="empresa",
        verbose_name=_("Origen del material"),
    )
    cantidad_teorica = models.DecimalField(
        max_digits=12, decimal_places=4, verbose_name=_("Cantidad teórica")
    )
    cantidad_consumida_real = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        blank=True,
        null=True,
        verbose_name=_("Cantidad real consumida (Merma)"),
    )
    costo_facturado_fason = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("Costo facturado por Fasón"),
    )
    costo_unitario_congelado = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Costo unitario (Congelado)"),
        help_text=_(
            "Snapshot del costo al emitir la e-OP (Garantiza inmutabilidad del Título de Crédito)."
        ),
    )
    subtotal_congelado = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Subtotal insumo (Congelado)"),
    )

    class Meta:
        verbose_name = _("Insumo requerido de OP")
        verbose_name_plural = _("Insumos requeridos de OP")

    def __str__(self):
        return f"Req: {self.insumo} ({self.cantidad_teorica}) para {self.op.numero}"

    @property
    def alerta_desvio_merma(self):
        """Indica si el consumo real superó el límite técnico tolerable (teórico + merma INTI)."""
        if self.cantidad_consumida_real is None:
            return False
        tolerancia_pct = Decimal("10.00")
        if self.op.receta:
            ri = self.op.receta.insumos.filter(insumo=self.insumo).first()
            if ri and ri.porcentaje_merma_tolerada:
                tolerancia_pct = ri.porcentaje_merma_tolerada
        limite_max = self.cantidad_teorica * (
            Decimal("1.0") + (tolerancia_pct / Decimal("100.0"))
        )
        return self.cantidad_consumida_real > limite_max


class OPParteProduccion(TimeStampedModel):
    """
    Parte o declaración parcial de producción con imputación de unidades y scrap.
    Permite declarar que se terminaron X pares de ciertas variantes, generando el alta
    inmediata en stock y el consumo proporcional de los insumos.
    """

    op = models.ForeignKey(
        OrdenProduccion,
        on_delete=models.CASCADE,
        related_name="partes_produccion_global",
        verbose_name=_("Orden de producción"),
    )
    etapa_tracking = models.ForeignKey(
        "OPEtapaTracking",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partes_produccion",
        verbose_name=_("Etapa de Tracking Asociada"),
        help_text=_(
            "Permite imputar el avance físico directamente a una etapa específica (Ej: Aparado)."
        ),
    )
    numero_parte = models.CharField(
        max_length=50, blank=True, verbose_name=_("N° de Parte")
    )
    fecha = models.DateTimeField(auto_now_add=True, verbose_name=_("Fecha de registro"))
    responsable = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Responsable"),
    )
    movimiento_terminados = models.ForeignKey(
        "inventario.MovimientoStock",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partes_ingreso_op",
        verbose_name=_("Remito de ingreso terminado"),
    )
    observaciones = models.TextField(
        blank=True, null=True, verbose_name=_("Observaciones")
    )

    # PoPW: Prueba de Trabajo Productivo
    ubicacion_gps_declarada = models.PointField(
        srid=4326,
        blank=True,
        null=True,
        verbose_name=_("Ubicación GPS al declarar"),
        help_text=_(
            "Coordenada exacta del dispositivo al reportar este avance (anti-spoofing)"
        ),
    )
    hash_validacion_biometrica = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name=_("Hash Validación Biométrica"),
        help_text=_("Hash del token devuelto por RENAPER / Servicio Liveness"),
    )

    class Meta:
        verbose_name = _("Parte de Producción")
        verbose_name_plural = _("Partes de Producción")
        ordering = ["-fecha"]

    def __str__(self):
        return f"Parte {self.numero_parte or self.id} - OP {self.op.numero}"

    def save(self, *args, **kwargs):
        if not self.numero_parte:
            self.numero_parte = SecuenciaService.obtener_siguiente_numero(
                "produccion.parte"
            )
        super().save(*args, **kwargs)


class OPParteProduccionLinea(TimeStampedModel):
    """Línea de cantidades por variante terminadas en un parte específico."""

    parte = models.ForeignKey(
        OPParteProduccion,
        on_delete=models.CASCADE,
        related_name="lineas",
        verbose_name=_("Parte de producción"),
    )
    variacion = models.ForeignKey(
        OPVariacion,
        on_delete=models.RESTRICT,
        related_name="partes_lineas",
        verbose_name=_("Variación de OP"),
    )
    cantidad = models.PositiveIntegerField(
        verbose_name=_("Cantidad primera selección"),
        help_text=_("Pares terminados de primera calidad"),
    )
    cantidad_segunda = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Cantidad segunda selección"),
        help_text=_(
            "Pares terminados con detalles estéticos para canal outlet/descuento"
        ),
    )
    cantidad_descarte = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Cantidad descartada / Scrap"),
        help_text=_("Pares arruinados o irrecuperables en esta tanda"),
    )

    class Meta:
        verbose_name = _("Línea de Parte de Producción")
        verbose_name_plural = _("Líneas de Partes de Producción")

    def __str__(self):
        seg = f" (+{self.cantidad_segunda} seg)" if self.cantidad_segunda else ""
        des = f" (+{self.cantidad_descarte} desc)" if self.cantidad_descarte else ""
        return f"{self.variacion.producto}: {self.cantidad} u 1ra{seg}{des}"


class OPEtapaTracking(TimeStampedModel):
    """Seguimiento en tiempo real de cada proceso y tallerista asignado."""

    ESTADO_ETAPA_CHOICES = [
        ("pendiente", _("Pendiente")),
        ("en_curso", _("En Curso")),
        ("pausada", _("Pausada / Inconveniente")),
        ("finalizada", _("Finalizada")),
    ]

    op = models.ForeignKey(
        OrdenProduccion,
        on_delete=models.CASCADE,
        related_name="tracking_etapas",
        verbose_name=_("Orden de producción"),
    )
    etapa_origen = models.ForeignKey(
        RecetaEtapa,
        on_delete=models.RESTRICT,
        related_name="trackings",
        verbose_name=_("Etapa de origen"),
    )
    tallerista_asignado = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="etapas_asignadas",
        verbose_name=_("Tallerista asignado"),
    )
    remito_traslado = models.ForeignKey(
        "inventario.MovimientoStock",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etapas_taller",
        verbose_name=_("Remito de traslado a taller"),
        help_text=_("Remito de traslado de corte/piezas hacia el tallerista externo"),
    )
    remito_retorno = models.ForeignKey(
        "inventario.MovimientoStock",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etapas_retorno_taller",
        verbose_name=_("Remito de retorno de taller"),
        help_text=_(
            "Remito que ampara el reingreso del lote semielaborado desde el taller externo a planta"
        ),
    )
    responsable_interno = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etapas_supervisadas",
        verbose_name=_("Supervisor interno Indino"),
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_ETAPA_CHOICES,
        default="pendiente",
        verbose_name=_("Estado de etapa"),
    )
    costo_servicio_total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("Liquidación total del servicio"),
    )

    class Meta:
        verbose_name = _("Tracking de etapa de OP")
        verbose_name_plural = _("Tracking de etapas de OP")

    def __str__(self):
        taller = f" -> {self.tallerista_asignado}" if self.tallerista_asignado else ""
        return f"{self.op.numero} | {self.etapa_origen.servicio.nombre}{taller}"

    def generar_remito_traslado_taller(self, origen=None, destino=None, usuario=None):
        """
        Genera el remito de traslado físico de piezas semielaboradas hacia el tallerista externo.
        """
        if not origen:
            origen, _ = Ubicacion.objects.get_or_create(
                tipo="interna", defaults={"nombre": "Almacén Principal", "activa": True}
            )
        if not destino:
            # Buscamos o creamos la ubicación tipo fason asociada a este tallerista
            destino, _ = Ubicacion.objects.get_or_create(
                tipo="fason",
                contacto=self.tallerista_asignado,
                defaults={
                    "nombre": f"Taller: {self.tallerista_asignado}"
                    if self.tallerista_asignado
                    else "Taller Externo",
                    "activa": True,
                },
            )

        clausula_legal = (
            "\n[Resguardo Jurídico]: Mercadería remitida bajo contrato de Locación de Obra (Arts. 1251 y ss. CCCN) "
            "y Depósito Regular en Custodia (Arts. 1356 y ss. CCCN). Las materias primas y semielaborados son propiedad "
            "inembargable y exclusiva del comitente emisor. El receptor actúa únicamente como custodio y transformador del material."
        )

        ct = ContentType.objects.get_for_model(self.op)

        remito = MovimientoStock.objects.create(
            numero=f"TRA-{self.op.numero}-E{self.etapa_origen.orden_ejecucion}",
            tipo="traslado",
            estado="confirmado",
            contacto=self.tallerista_asignado,
            ubicacion_origen=origen,
            ubicacion_destino=destino,
            responsable=usuario or self.responsable_interno,
            content_type_origen=ct,
            object_id_origen=self.op.id,
            documento_origen=self.op.numero,
            observaciones=f"Traslado de piezas para etapa '{self.etapa_origen.servicio.nombre}' de OP {self.op.numero}. {clausula_legal}",
        )
        self.remito_traslado = remito
        self.save()
        return remito

    def generar_remito_retorno_taller(self, origen=None, destino=None, usuario=None):
        """
        Genera el remito de reingreso físico de piezas semielaboradas desde el taller externo a planta.
        """
        if not origen:
            origen, _ = Ubicacion.objects.get_or_create(
                tipo="fason",
                contacto=self.tallerista_asignado,
                defaults={
                    "nombre": f"Taller: {self.tallerista_asignado}"
                    if self.tallerista_asignado
                    else "Taller Externo",
                    "activa": True,
                },
            )
        if not destino:
            destino, _ = Ubicacion.objects.get_or_create(
                tipo="interna", defaults={"nombre": "Almacén Principal", "activa": True}
            )

        ct = ContentType.objects.get_for_model(self.op)

        remito = MovimientoStock.objects.create(
            numero=f"RET-{self.op.numero}-E{self.etapa_origen.orden_ejecucion}",
            tipo="traslado",
            estado="confirmado",
            contacto=self.tallerista_asignado,
            ubicacion_origen=origen,
            ubicacion_destino=destino,
            responsable=usuario or self.responsable_interno,
            content_type_origen=ct,
            object_id_origen=self.op.id,
            documento_origen=self.op.numero,
            observaciones=f"Retorno de piezas terminadas de etapa '{self.etapa_origen.servicio.nombre}' de OP {self.op.numero}",
        )
        self.remito_retorno = remito
        self.save()
        return remito

    @property
    def etapa_anterior(self):
        """Retorna la etapa de tracking inmediatamente anterior basada en el orden de ejecución."""
        return (
            self.op.tracking_etapas.filter(
                etapa_origen__orden_ejecucion__lt=self.etapa_origen.orden_ejecucion
            )
            .order_by("-etapa_origen__orden_ejecucion")
            .first()
        )

    @property
    def capacidad_maxima_por_insumos(self):
        """
        Calcula el techo máximo de unidades producibles en función de la materia prima
        despachada al taller en custodia (BOM Yield Cap).
        Ejemplo: Si se remitieron 20 m de cuero y cada par consume 0.4 m, el techo es 50 pares.
        Retorna un dict con {'capacidad_maxima': int|None, 'insumo_limitante': str|None, 'detalle': list}
        """
        if not self.op.receta:
            return {"capacidad_maxima": None, "insumo_limitante": None, "detalle": []}

        # Buscamos la ubicación de custodia del tallerista asignado
        ubicacion_fason = None
        if self.tallerista_asignado:
            ubicacion_fason = Ubicacion.objects.filter(
                tipo="fason",
                contacto=self.tallerista_asignado,
            ).first()

        capacidad_minima = None
        insumo_limitante = None
        detalle = []

        for req in self.op.insumos_requeridos.filter(origen="empresa"):
            receta_insumo = self.op.receta.insumos.filter(insumo=req.insumo).first()
            if not receta_insumo or receta_insumo.cantidad <= 0:
                continue

            consumo_unitario = receta_insumo.cantidad

            # Buscamos cuánto de este insumo fue efectivamente despachado para esta OP
            # a través de remitos de traslado hacia el taller o fábrica
            ct_op = ContentType.objects.get_for_model(self.op)
            despachado = LineaMovimientoStock.objects.filter(
                movimiento__content_type_origen=ct_op,
                movimiento__object_id_origen=self.op.id,
                movimiento__tipo="traslado",
                movimiento__estado__in=["confirmado", "finalizado"],
                producto=req.insumo,
            ).aggregate(total=models.Sum("cantidad_hecha"))["total"] or Decimal("0.0")

            # Si no hay remito individualizado pero hay stock en quant del taller, consultamos el quant
            if despachado <= 0 and ubicacion_fason:
                quant = StockQuant.objects.filter(
                    producto=req.insumo,
                    ubicacion=ubicacion_fason,
                ).first()
                if quant:
                    despachado = quant.cantidad_fisica

            if despachado > 0:
                unidades_posibles = int(despachado // consumo_unitario)
                detalle.append(
                    {
                        "insumo": req.insumo.nombre,
                        "despachado": despachado,
                        "consumo_unitario": consumo_unitario,
                        "unidades_posibles": unidades_posibles,
                    }
                )
                if capacidad_minima is None or unidades_posibles < capacidad_minima:
                    capacidad_minima = unidades_posibles
                    insumo_limitante = req.insumo.nombre

        return {
            "capacidad_maxima": capacidad_minima,
            "insumo_limitante": insumo_limitante,
            "detalle": detalle,
        }

    @property
    def unidades_habilitadas_para_declarar(self):
        """
        Retorna la cantidad máxima acumulada de unidades que pueden ser declaradas en esta etapa.
        - Si es la primera etapa: el límite es el mínimo entre la cantidad planificada de la OP
          y el rendimiento de los insumos despachados al taller (Yield Cap).
        - Si es una etapa intermedia: el límite es lo procesado por la etapa inmediatamente anterior.
        """
        ant = self.etapa_anterior
        if not ant:
            total_planificado = (
                self.op.variaciones.aggregate(total=models.Sum("cantidad"))["total"]
                or self.op.cantidad_total
                or 0
            )
            yield_cap = self.capacidad_maxima_por_insumos["capacidad_maxima"]
            if yield_cap is not None:
                return min(total_planificado, yield_cap)
            return total_planificado

        # Para etapas subsecuentes, manda lo aprobado en la etapa anterior (1ra + 2da)
        total_primera = (
            ant.partes_produccion.aggregate(t=models.Sum("lineas__cantidad"))["t"] or 0
        )
        total_segunda = (
            ant.partes_produccion.aggregate(t=models.Sum("lineas__cantidad_segunda"))[
                "t"
            ]
            or 0
        )
        return total_primera + total_segunda

    @property
    def unidades_ya_declaradas(self):
        """Retorna cuántas unidades ya fueron declaradas y procesadas en esta etapa."""
        total_primera = (
            self.partes_produccion.aggregate(t=models.Sum("lineas__cantidad"))["t"] or 0
        )
        total_segunda = (
            self.partes_produccion.aggregate(t=models.Sum("lineas__cantidad_segunda"))[
                "t"
            ]
            or 0
        )
        total_descarte = (
            self.partes_produccion.aggregate(t=models.Sum("lineas__cantidad_descarte"))[
                "t"
            ]
            or 0
        )
        return total_primera + total_segunda + total_descarte


class OPEtapaLog(TimeStampedModel):
    """Bitácora inmutable de eventos y cambios de estado en las etapas."""

    etapa_tracking = models.ForeignKey(
        OPEtapaTracking,
        on_delete=models.CASCADE,
        related_name="logs",
        verbose_name=_("Etapa de tracking"),
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("Usuario responsable"),
    )
    estado_anterior = models.CharField(
        max_length=20, blank=True, null=True, verbose_name=_("Estado previo")
    )
    estado_nuevo = models.CharField(max_length=20, verbose_name=_("Estado nuevo"))
    observacion = models.TextField(verbose_name=_("Observación del cambio"))

    class Meta:
        verbose_name = _("Log de etapa de OP")
        verbose_name_plural = _("Logs de etapas de OP")
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.creado_en.strftime('%d/%m %H:%M')} - {self.usuario} -> {self.estado_nuevo}"


class OPEscrowHito(TimeStampedModel):
    """
    Representa una línea del contrato inteligente de la e-OP.
    Bloquea los fondos en fideicomiso (FDI) hasta que se cumpla la condición técnica,
    permitiendo pagos escalonados de forma descentralizada.
    """

    op = models.ForeignKey(
        OrdenProduccion,
        on_delete=models.CASCADE,
        related_name="escrow_hitos",
        verbose_name=_("Orden de producción"),
    )
    etapa_tracking = models.ForeignKey(
        OPEtapaTracking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hitos_escrow",
        verbose_name=_("Etapa Productiva Asignada"),
    )
    beneficiario = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="hitos_escrow_cobrar",
        verbose_name=_("Tallerista / Beneficiario del Hito"),
        help_text=_(
            "El CBU/CVU de este contacto recibirá el pago al liberarse el hito"
        ),
    )
    nombre_hito = models.CharField(
        max_length=100, verbose_name=_("Hito de Pago (Ej: Hito Cero, Corte)")
    )
    condicion_disparo = models.CharField(
        max_length=200, verbose_name=_("Condición de Disparo Técnico")
    )
    porcentaje_tramo = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name=_("% del Tramo")
    )
    monto_bruto_retenido = models.DecimalField(
        max_digits=15, decimal_places=2, verbose_name=_("Monto Bruto Retenido")
    )
    fecha_liberacion_estimada = models.DateField(
        null=True, blank=True, verbose_name=_("Fecha de Liberación Estimada")
    )
    fecha_liberacion_real = models.DateField(
        null=True, blank=True, verbose_name=_("Fecha de Liberación Real")
    )
    estado = models.CharField(
        max_length=20,
        choices=[
            ("retenido", _("Retenido en Escrow FDI")),
            ("liberado", _("Acreditado (Liberado)")),
            ("en_disputa", _("En Disputa / Congelado")),
        ],
        default="retenido",
        verbose_name=_("Estado del Hito"),
    )
    comprobante_bancario = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Constancia Bancaria / BAPRO TX"),
    )

    class Meta:
        verbose_name = _("Hito de Escrow e-OP")
        verbose_name_plural = _("Hitos de Escrow e-OP")
        ordering = ["id"]

    def __str__(self):
        return f"{self.op.numero} - {self.nombre_hito} ({self.estado})"
