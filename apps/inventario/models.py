from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from apps.base.models import TimeStampedModel, DocumentoBase


class Categoria(TimeStampedModel):
    nombre = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subcategorias",
    )

    def __str__(self):
        return self.nombre


class UnidadMedida(TimeStampedModel):
    """
    Unidad de medida para inventario, producción y ventas (Odoo: uom.uom).
    Permite definir unidades dinámicas (ej: Metros, Pares, Rollos, Litros).
    """
    TIPO_CHOICES = [
        ('unidad', _('Unidad / Cantidad')),
        ('longitud', _('Longitud / Distancia')),
        ('peso', _('Peso / Masa')),
        ('volumen', _('Volumen / Capacidad')),
        ('tiempo', _('Tiempo')),
    ]

    nombre = models.CharField(max_length=50, unique=True, verbose_name=_('Nombre'))
    simbolo = models.CharField(max_length=10, unique=True, verbose_name=_('Símbolo / Abreviatura'))
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='unidad', verbose_name=_('Tipo de medida'))
    activa = models.BooleanField(default=True, verbose_name=_('Activa'))

    class Meta:
        verbose_name = _('Unidad de medida')
        verbose_name_plural = _('Unidades de medida')
        ordering = ['tipo', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.simbolo})"


class ProductoTemplate(TimeStampedModel):
    TIPO_PRODUCTO_CHOICES = [
        ("almacenable", "Almacenable (Storable)"),
        ("consumible", "Consumible (Consumable)"),
        ("servicio", "Servicio (Service)"),
    ]

    nombre = models.CharField(max_length=200)
    codigo_interno = models.CharField(max_length=50, unique=True, null=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True)
    descripcion = models.TextField(blank=True, null=True)
    tipo_producto = models.CharField(
        max_length=20, choices=TIPO_PRODUCTO_CHOICES, default="almacenable"
    )
    unidad_medida = models.ForeignKey(
        UnidadMedida,
        on_delete=models.RESTRICT,
        related_name="productos",
        verbose_name=_("Unidad de medida"),
        help_text=_("Unidad física en la que se cuenta o mide este producto"),
    )

    precio = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("0.00")
    )
    costo = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("0.00")
    )

    # Define si el producto se trackea por lote, número de serie, o nada
    TRACKING_CHOICES = [
        ("none", "Sin seguimiento"),
        ("lote", "Por Lotes"),
        ("serie", "Por Número de Serie Unico"),
    ]
    tracking = models.CharField(max_length=10, choices=TRACKING_CHOICES, default="none")

    # Reglas básicas de reabastecimiento / stock de seguridad
    stock_minimo = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0"),
        verbose_name=_("Stock mínimo / Punto de pedido"),
        help_text=_("Cantidad mínima recomendada en almacén para disparar compras o fabricación"),
    )
    stock_maximo = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0"),
        verbose_name=_("Stock máximo sugerido"),
        help_text=_("Límite superior deseado para evitar sobrestock e inmovilización de capital"),
    )

    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

    @property
    def alerta_stock_minimo(self):
        """Indica si el stock total disponible consolidado en almacenes internos está por debajo del mínimo."""
        if self.stock_minimo <= Decimal("0.0"):
            return False
        total_disp = self.productos.filter(
            quants__ubicacion__tipo="interna"
        ).aggregate(
            total=models.Sum(models.F("quants__cantidad_fisica") - models.F("quants__cantidad_reservada"))
        )["total"] or Decimal("0.0")
        return total_disp < self.stock_minimo


class Atributo(TimeStampedModel):
    nombre = models.CharField(max_length=50)  # Ej: Talle, Color

    def __str__(self):
        return self.nombre


class AtributoValor(TimeStampedModel):
    atributo = models.ForeignKey(
        Atributo, on_delete=models.CASCADE, related_name="valores"
    )
    valor = models.CharField(max_length=50)  # Ej: 39, 40, Negro, Marrón

    def __str__(self):
        return f"{self.atributo.nombre}: {self.valor}"


class Producto(TimeStampedModel):
    template = models.ForeignKey(
        ProductoTemplate, on_delete=models.CASCADE, related_name="variantes"
    )
    valores_atributo = models.ManyToManyField(AtributoValor, blank=True)

    sku = models.CharField(max_length=100, unique=True)
    codigo_barras = models.CharField(max_length=100, blank=True, null=True)

    # El recargo que tiene esta variante específica sobre el precio base del template
    precio_extra = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("0.00")
    )

    def __str__(self):
        if self.valores_atributo.exists():
            atributos_str = " - ".join([av.valor for av in self.valores_atributo.all()])
            return f"{self.template.nombre} ({atributos_str})"
        return self.template.nombre


# ==========================================
# MOTOR DE INVENTARIO (PARTIDA DOBLE, QUANTS Y LOTES)
# ==========================================


class Ubicacion(TimeStampedModel):
    TIPO_UBICACION_CHOICES = [
        ("interna", "Ubicación Física"),
        ("fason", "Taller Externo / Fasón (Terceros)"),
        ("proveedor", "Virtual: Proveedor"),
        ("cliente", "Virtual: Cliente"),
        ("produccion", "Virtual: Producción"),
        ("ajuste", "Virtual: Ajuste/Pérdida"),
    ]

    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPO_UBICACION_CHOICES)
    contacto = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ubicaciones",
        verbose_name=_("Contacto / Tallerista responsable"),
        help_text=_("Asigna esta ubicación al tallerista o proveedor custodio de la mercadería"),
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Ubicación")
        verbose_name_plural = _("Ubicaciones")

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


class Lote(TimeStampedModel):
    """Identifica un lote específico de manufactura o compra para un Producto"""

    numero = models.CharField(max_length=100, unique=True, help_text="Ej: LOTE-24-10-A")
    producto = models.ForeignKey(
        Producto, on_delete=models.CASCADE, related_name="lotes"
    )
    referencia_externa = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.numero


class StockQuant(TimeStampedModel):
    """
    La "foto" actual (Snapshot).
    Evita tener que sumar miles de movimientos cada vez que quieres ver el stock.
    Se actualiza automáticamente cuando un MovimientoStock pasa a estado 'realizado'.
    """

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    ubicacion = models.ForeignKey(Ubicacion, on_delete=models.CASCADE)
    lote = models.ForeignKey(Lote, on_delete=models.CASCADE, blank=True, null=True)

    cantidad_fisica = models.DecimalField(max_digits=12, decimal_places=4, default=0.0)
    cantidad_reservada = models.DecimalField(
        max_digits=12, decimal_places=4, default=0.0
    )

    class Meta:
        # Solo puede haber un quant (registro) por combinación exacta de producto + ubicacion + lote
        unique_together = ("producto", "ubicacion", "lote")

    @property
    def cantidad_disponible(self):
        return self.cantidad_fisica - self.cantidad_reservada

    def __str__(self):
        lote_str = f" [Lote: {self.lote.numero}]" if self.lote else ""
        uom_str = self.producto.template.unidad_medida.simbolo if self.producto.template.unidad_medida else ""
        return f"{self.cantidad_fisica} {uom_str} - {self.producto}{lote_str} en {self.ubicacion.nombre}"


class MovimientoStock(DocumentoBase):
    """
    Cabecera (Agrupador de líneas). El documento físico (Remito / Picking).
    Hereda de DocumentoBase: numero, fecha, estado, observaciones, creado_en, modificado_en.
    """

    TIPO_MOVIMIENTO_CHOICES = [
        ("recepcion", "Recepción (Ingreso)"),
        ("entrega", "Entrega (Salida)"),
        ("traslado", "Traslado Interno"),
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_MOVIMIENTO_CHOICES)
    es_fiscal = models.BooleanField(
        default=False, help_text="True = Remito 'R' AFIP. False = Remito 'X' Interno"
    )

    contacto = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="movimientos_stock",
        verbose_name="Contacto",
    )

    # Ubicaciones globales por defecto para este documento
    ubicacion_origen = models.ForeignKey(
        Ubicacion, on_delete=models.RESTRICT, related_name="movimientos_origen"
    )
    ubicacion_destino = models.ForeignKey(
        Ubicacion, on_delete=models.RESTRICT, related_name="movimientos_destino"
    )

    responsable = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    documento_origen = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("Documento de origen"),
        help_text=_("Referencia a la OC, OP o Pedido generador, ej: OC-0001, OP-0042, PED-0100"),
    )
    backorder_de = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backorders",
        verbose_name=_("Backorder de"),
        help_text=_("Remito original del cual este movimiento es saldo remanente pendiente"),
    )

    class Meta(DocumentoBase.Meta):
        verbose_name = "Movimiento de stock"
        verbose_name_plural = "Movimientos de stock"

    def __str__(self):
        fiscal = "Fiscal" if self.es_fiscal else "X"
        backorder_str = f" [Backorder de {self.backorder_de.numero}]" if self.backorder_de else ""
        return f"{self.numero}{backorder_str} ({self.get_tipo_display()} - {fiscal}) [{self.get_estado_display()}]"

    def dividir_backorder(self, cantidades_realizadas, usuario=None):
        """
        Aplica el patrón estándar Backorder de Odoo para recepciones, entregas o traslados parciales.
        - cantidades_realizadas: dict con {linea_id: cantidad_real_efectuada}
        - Si para alguna línea la cantidad realizada es menor a la cantidad demandada:
          1. Crea un nuevo MovimientoStock remanente (Backorder) en estado 'confirmado' para el saldo.
          2. Ajusta la cantidad de la línea actual a lo realmente efectuado.
          3. Pasa el movimiento actual y sus líneas procesadas a 'realizado'/'finalizado'.
        """
        from django.db import transaction
        with transaction.atomic():
            hay_remanente = False
            lineas_remanentes = []

            for linea in self.lineas.all():
                qty_solicitada = linea.cantidad
                qty_real = Decimal(str(cantidades_realizadas.get(linea.id, qty_solicitada)))

                if qty_real < qty_solicitada:
                    remanente = qty_solicitada - qty_real
                    if remanente > 0:
                        hay_remanente = True
                        lineas_remanentes.append((linea, remanente))
                        linea.cantidad = qty_real
                        linea.cantidad_hecha = qty_real
                        linea.save()
                else:
                    linea.cantidad_hecha = qty_real
                    linea.save()

            backorder_obj = None
            if hay_remanente:
                # Contamos cuántos backorders tiene para numerar correlativo (ej: REM-0001-B1)
                num_backorder = self.backorders.count() + 1
                backorder_numero = f"{self.numero}-B{num_backorder}"

                backorder_obj = MovimientoStock.objects.create(
                    numero=backorder_numero,
                    tipo=self.tipo,
                    es_fiscal=self.es_fiscal,
                    contacto=self.contacto,
                    ubicacion_origen=self.ubicacion_origen,
                    ubicacion_destino=self.ubicacion_destino,
                    responsable=usuario or self.responsable,
                    documento_origen=self.documento_origen or self.numero,
                    backorder_de=self,
                    estado="confirmado",
                    observaciones=f"Backorder remanente generado por entrega parcial de {self.numero}",
                )

                for linea_orig, rem_qty in lineas_remanentes:
                    LineaMovimientoStock.objects.create(
                        movimiento=backorder_obj,
                        producto=linea_orig.producto,
                        cantidad=rem_qty,
                        lote=linea_orig.lote,
                        ubicacion_origen=linea_orig.ubicacion_origen,
                        ubicacion_destino=linea_orig.ubicacion_destino,
                        estado="borrador" if self.estado == "borrador" else "reservado",
                        referencia=f"Remanente de {linea_orig.referencia or self.numero}",
                    )

            # Finalizamos el movimiento actual y sus líneas efectuadas
            self.estado = "finalizado"
            self.save()
            for linea in self.lineas.all():
                linea.estado = "realizado"
                linea.save()

            return backorder_obj


class LineaMovimientoStock(TimeStampedModel):
    """
    La línea específica que mueve una cantidad de producto (Odoo: stock.move).
    Hereda de TimeStampedModel: creado_en, modificado_en.
    """

    ESTADO_CHOICES = [
        ("borrador", "Borrador"),
        ("reservado", "Reservado (Impacta Quant Reservado)"),
        ("realizado", "Realizado (Impacta Quant Físico)"),
        ("cancelado", "Cancelado"),
    ]

    movimiento = models.ForeignKey(
        MovimientoStock, on_delete=models.CASCADE, related_name="lineas"
    )

    producto = models.ForeignKey(Producto, on_delete=models.RESTRICT)
    cantidad = models.DecimalField(max_digits=12, decimal_places=4, verbose_name=_("Cantidad demandada"))
    cantidad_hecha = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0"),
        verbose_name=_("Cantidad realizada / recibida"),
        help_text=_("Cantidad física efectivamente operada en esta línea"),
    )
    lote = models.ForeignKey(
        Lote,
        on_delete=models.RESTRICT,
        blank=True,
        null=True,
        help_text="Obligatorio si el producto trackea por lote",
    )

    # Redundancia intencional: Por defecto, heredan de MovimientoStock, pero permiten granularidad
    ubicacion_origen = models.ForeignKey(
        Ubicacion,
        on_delete=models.RESTRICT,
        related_name="lineas_salida",
        blank=True,
        null=True,
    )
    ubicacion_destino = models.ForeignKey(
        Ubicacion,
        on_delete=models.RESTRICT,
        related_name="lineas_entrada",
        blank=True,
        null=True,
    )

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="borrador")
    fecha_efectiva = models.DateTimeField(blank=True, null=True)
    responsable = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    referencia = models.CharField(
        max_length=100, blank=True, help_text="Ej: OP-001, Factura-X, Ajuste-2024"
    )

    class Meta:
        verbose_name = "Línea de movimiento de stock"
        verbose_name_plural = "Líneas de movimiento de stock"
        ordering = ["-creado_en"]

    def save(self, *args, **kwargs):
        # Autocompletar ubicaciones desde la cabecera si están vacías
        if not self.ubicacion_origen and self.movimiento:
            self.ubicacion_origen = self.movimiento.ubicacion_origen
        if not self.ubicacion_destino and self.movimiento:
            self.ubicacion_destino = self.movimiento.ubicacion_destino
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cantidad} {self.producto} ({self.get_estado_display()})"
