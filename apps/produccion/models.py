import hashlib
import json
import uuid
from decimal import Decimal
from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from apps.base.models import TimeStampedModel, DocumentoBase
from apps.inventario.models import ProductoTemplate, Producto, AtributoValor


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
    Hereda de DocumentoBase: numero, fecha, estado (borrador, confirmado, cancelado, anulado),
    observaciones, creado_en, modificado_en.
    """

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

    ESTADO_ESCROW_CHOICES = [
        ("no_aplica", _("No Aplica (Interna)")),
        ("fondeado", _("Escrow Fondeado (Pendiente MES)")),
        ("aprobado_silencio", _("Aprobado por Silencio (48h)")),
        ("vetado_mes", _("Vetado por la MES")),
        ("hito_cero_liberado", _("Hito Cero Liberado al Taller")),
        ("en_disputa", _("En Disputa (Interviene PTF)")),
        ("finalizado", _("Escrow Liquidado Totalmente")),
    ]

    fecha_entrega = models.DateField(
        blank=True, null=True, verbose_name=_("Fecha est. entrega")
    )
    receta = models.ForeignKey(
        Receta,
        on_delete=models.RESTRICT,
        related_name="ordenes_produccion",
        verbose_name=_("Receta base"),
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
    estado_escrow = models.CharField(
        max_length=30,
        choices=ESTADO_ESCROW_CHOICES,
        default="no_aplica",
        verbose_name=_("Estado Escrow (Protocolo e-OP)"),
    )
    fecha_fondeo_escrow = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Fecha de Fondeo (Inicio Timelock 48h)")
    )

    # Identidad digital y seguridad jurídica de la e-OP
    uuid_identificador = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("Identificador Único e-OP"),
    )
    hash_seguridad = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        verbose_name=_("Hash Criptográfico e-OP"),
        help_text=_(
            "Digest SHA-256 inmutable generado al confirmar la orden para interoperabilidad crediticia y verificación de autenticidad"
        ),
    )
    regimen_juridico = models.CharField(
        max_length=40,
        choices=[
            ("fason_locacion_obra", _("Façón / Locación de Obra (Arts. 1251 CCCN)")),
            (
                "maquila_industrial",
                _("Maquila Industrial (Proyecto Reforma Ley 25.113)"),
            ),
            ("produccion_propia", _("Producción Integrada en Planta")),
        ],
        default="fason_locacion_obra",
        verbose_name=_("Régimen Jurídico"),
    )
    clausula_inembargabilidad = models.BooleanField(
        default=True,
        verbose_name=_("Amparado bajo Inembargabilidad de Stock"),
        help_text=_(
            "Declara las materias primas y semielaborados como propiedad inembargable del comitente emisor"
        ),
    )
    # === Protocolo e-OP ===
    # K_T: Tallerista / Custodio principal
    tallerista_principal = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="ops_como_tallerista",
        verbose_name=_("Tallerista / Fasón Principal"),
        help_text=_("Responsable primario ante el protocolo de custodia y liquidación"),
    )

    # Vector C: Desglose Factorial de Costos Inmutable (en UCI o ARS indexado)
    costo_mod = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.0"),
        verbose_name=_("Mano de Obra Directa (MOD)"),
    )
    costo_cs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.0"),
        verbose_name=_("Cargas Sociales (CS)"),
    )
    costo_bom = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.0"),
        verbose_name=_("Insumos (BOM)"),
    )
    costo_gg = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.0"),
        verbose_name=_("Gastos Generales / Amortización (GG)"),
    )
    costo_fdi = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.0"),
        verbose_name=_("Reserva FDI (2%)"),
    )
    costo_tax = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.0"),
        verbose_name=_("Impuestos / Monotributo (TAX)"),
    )
    costo_mg = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.0"),
        verbose_name=_("Margen (MG)"),
    )

    # Sigma: Firmas Criptográficas
    firmas_digitales = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            "Esquema Multifirma 2-de-3: {'comitente': 'sig_hash', 'tallerista': 'sig_hash', 'arbitro': 'sig_hash'}"
        ),
    )

    es_sello_buen_diseno = models.BooleanField(
        default=False,
        verbose_name=_("Distinción Sello Buen Diseño (SBD)"),
        help_text=_("Habilita condiciones preferenciales de financiamiento o anticipo"),
    )

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
        Registra la finalización parcial de una tanda de la OP (Odoo MRP).
        - variaciones_cantidades: dict con {op_variacion_id: cantidad_producida}
        """
        from django.db import transaction
        from apps.inventario.models import (
            Ubicacion,
            MovimientoStock,
            LineaMovimientoStock,
        )

        with transaction.atomic():
            almacen, _ = Ubicacion.objects.get_or_create(
                tipo="interna", defaults={"nombre": "Almacén Principal", "activa": True}
            )
            ubicacion_produccion, _ = Ubicacion.objects.get_or_create(
                tipo="produccion",
                defaults={"nombre": "Fábrica (Virtual)", "activa": True},
            )

            num_parte = self.partes_produccion.count() + 1
            remito_terminados = MovimientoStock.objects.create(
                numero=f"ING-{self.numero}-P{num_parte}",
                tipo="recepcion",
                estado="finalizado",
                ubicacion_origen=ubicacion_produccion,
                ubicacion_destino=almacen,
                contacto=self.cliente,
                responsable=usuario,
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
            if remito_reserva and self.cantidad_total > 0:
                factor = Decimal(total_tanda) / Decimal(self.cantidad_total)
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
        from django.db import transaction
        from apps.inventario.models import MovimientoStock

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
        from django.db import transaction
        from apps.inventario.models import (
            Ubicacion,
            MovimientoStock,
            LineaMovimientoStock,
            Producto,
        )

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
            remito_dev = MovimientoStock.objects.create(
                numero=f"DEV-{self.numero}-{num_dev:02d}",
                tipo="traslado",
                estado="finalizado",
                ubicacion_origen=ubicacion_produccion,
                ubicacion_destino=almacen,
                responsable=usuario,
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

    def calcular_merkle_root_bom(self):
        """
        Calcula la Raíz del Árbol de Merkle para la lista de insumos (BOM) asignados a esta OP.
        Cumple con la especificación M_BOM del Protocolo e-OP usando la foto transaccional inmutable.
        """
        insumos = list(self.insumos_requeridos.all().order_by("id"))
        if not insumos:
            return None

        # Nivel de hojas (Leaves)
        hojas = []
        for req in insumos:
            # Usamos cantidad teórica y el insumo asociado
            data = f"{req.insumo_id}:{req.cantidad_teorica}"
            hojas.append(hashlib.sha256(data.encode("utf-8")).hexdigest())

        # Calcular raíz (implementación simplificada concatenando hashes)
        while len(hojas) > 1:
            if len(hojas) % 2 != 0:
                hojas.append(hojas[-1])  # Duplicar último si es impar
            siguiente_nivel = []
            for i in range(0, len(hojas), 2):
                combinado = hojas[i] + hojas[i + 1]
                siguiente_nivel.append(
                    hashlib.sha256(combinado.encode("utf-8")).hexdigest()
                )
            hojas = siguiente_nivel

        return hojas[0]

    def generar_payload_canonico(self):
        """
        Genera el payload canónico serializado para firma y hashing de la e-OP.
        Garantiza un formato JSON determinista ordenado por claves para interoperabilidad.
        """
        payload = {
            "uuid": str(self.uuid_identificador),
            "numero": self.numero,
            "fecha": str(self.fecha),
            "receta_id": self.receta_id,
            "cliente_id": self.cliente_id,
            "cantidad_total": self.cantidad_total,
            "regimen_juridico": self.regimen_juridico,
            "clausula_inembargabilidad": self.clausula_inembargabilidad,
            "merkle_root_bom": self.calcular_merkle_root_bom(),
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def calcular_hash_eop(self):
        """Calcula el hash SHA-256 canónico del documento e-OP."""
        payload_str = self.generar_payload_canonico()
        return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    def sellar_hash_eop(self):
        """
        Calcula y fija el hash criptográfico inmutable si aún no fue emitido.
        Se ejecuta al confirmar la orden para convertirla en e-OP inmutable y colateralizable.
        """
        if not self.hash_seguridad:
            self.hash_seguridad = self.calcular_hash_eop()
            self.save(update_fields=["hash_seguridad"])
        return self.hash_seguridad

    def verificar_integridad_hash(self):
        """
        Verifica si los datos canónicos de la OP coinciden con el hash sellado.
        Retorna True si no hubo alteraciones post-emisión.
        """
        if not self.hash_seguridad:
            return False
        return self.calcular_hash_eop() == self.hash_seguridad


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
        Producto, on_delete=models.RESTRICT, verbose_name=_("Insumo (SKU)")
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
    Parte o declaración parcial de producción (Odoo: mrp.production quantity producing).
    Permite declarar que se terminaron X pares de ciertas variantes, generando el alta
    inmediata en stock y el consumo proporcional de los insumos.
    """

    op = models.ForeignKey(
        OrdenProduccion,
        on_delete=models.CASCADE,
        related_name="partes_produccion",
        verbose_name=_("Orden de producción"),
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
        RecetaEtapa, on_delete=models.RESTRICT, verbose_name=_("Etapa de origen")
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
        from apps.inventario.models import Ubicacion, MovimientoStock

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

        remito = MovimientoStock.objects.create(
            numero=f"TRA-{self.op.numero}-E{self.etapa_origen.orden_ejecucion}",
            tipo="traslado",
            estado="confirmado",
            contacto=self.tallerista_asignado,
            ubicacion_origen=origen,
            ubicacion_destino=destino,
            responsable=usuario or self.responsable_interno,
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
        from apps.inventario.models import Ubicacion, MovimientoStock

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

        remito = MovimientoStock.objects.create(
            numero=f"RET-{self.op.numero}-E{self.etapa_origen.orden_ejecucion}",
            tipo="traslado",
            estado="confirmado",
            contacto=self.tallerista_asignado,
            ubicacion_origen=origen,
            ubicacion_destino=destino,
            responsable=usuario or self.responsable_interno,
            documento_origen=self.op.numero,
            observaciones=f"Retorno de piezas terminadas de etapa '{self.etapa_origen.servicio.nombre}' de OP {self.op.numero}",
        )
        self.remito_retorno = remito
        self.save()
        return remito


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
